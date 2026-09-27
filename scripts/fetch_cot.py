"""
Fetch CFTC Commitments of Traders data and compute the COT Index /
Sentiment Index (Larry Williams method, 52-week lookback) for the
markets listed in config.INDICATORS (source == "cot").

CFTC splits reportable markets across two different report types, each
with its own trader classification and its own file format - there is
no single file that covers everything:

  "legacy" - deacot{year}.zip, the old "Futures Only" report. Covers
             commodities (gold, crude oil, ...) and some financial
             markets, classified as Commercial / Non-Commercial /
             Non-Reportable. This is what CupSir's original "smart
             money" framework (commercial net position) assumes.
             cfg["report"] == "legacy".

  "tff"    - fut_fin_txt_{year}.zip, "Traders in Financial Futures".
             Covers currency/rate/equity-index futures (S&P 500, UST
             notes, USD Index, ...) - CFTC moved these out of the
             legacy report entirely. Classifies traders as Dealer /
             Asset Manager / Leveraged Funds / Other Reportable
             instead. There is no "Commercial" bucket here, so we
             approximate CupSir's framework as:
                 institutional/"smart money" net = Dealer + Asset Manager
                 speculative/"crowd" net         = Leveraged Funds
             (Dealer = bank/broker intermediaries hedging client flow,
             Asset Manager = institutional real-money accounts - both
             behave more like the legacy report's "commercial" side.
             Leveraged Funds = hedge funds/CTAs, the market's closest
             analogue to legacy's trend-following "non-commercial"
             crowd, which is what the Sentiment Index needs to be
             genuinely a *crowding* signal.)
             cfg["report"] == "tff".

Both report's real column headers and the exact TFF market names below
were confirmed against a live run's actual data on 2026-09-27 (not
guessed) - see git history for the debug trail; guessing at CFTC's
column-naming conventions has repeatedly been wrong.

Standalone usage (writes data/cot_cache.json for inspection):
    python scripts/fetch_cot.py

Library usage (called from build_dashboard.py):
    from fetch_cot import get_cot_results
    results = get_cot_results()   # {"cot_sp500": {...}, "cot_10y": {...}, ...}
"""
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from config import INDICATORS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

HEADERS = {
    # cftc.gov returns 403 to requests' default User-Agent on some networks
    # (including GitHub Actions runners) - a browser-like UA fixes it.
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/zip,application/octet-stream,*/*",
}

LEGACY_URL = "https://www.cftc.gov/files/dea/history/deacot{year}.zip"
LEGACY_COLUMN_MAP = {
    "Market and Exchange Names": "market",
    "As of Date in Form YYMMDD": "date",
    "Commercial Positions-Long (All)": "primary_long",
    "Commercial Positions-Short (All)": "primary_short",
    "Nonreportable Positions-Long (All)": "secondary_long",
    "Nonreportable Positions-Short (All)": "secondary_short",
}

TFF_URL = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"


def _download_zip_csv(url: str) -> pd.DataFrame:
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = z.namelist()
        txt_names = [f for f in names if f.lower().endswith(".txt")]
        if not txt_names:
            raise RuntimeError(f"no .txt in zip; namelist={names[:10]}")
        filename = txt_names[0]
        with z.open(filename) as f:
            df = pd.read_csv(f, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    return df


def _finish(df: pd.DataFrame, column_map: dict) -> pd.DataFrame:
    df = df.rename(columns=column_map)
    keep = list(dict.fromkeys(column_map.values()))  # de-dup, keep order
    missing = [c for c in keep if c not in df.columns]
    if missing:
        raise RuntimeError(f"missing {missing} after rename; raw_columns_sample={list(df.columns)[:20]}")
    df = df[keep].copy()
    numeric_cols = [c for c in keep if c not in ("market", "date")]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], format="%y%m%d", errors="coerce")
    return df.dropna(subset=["date"])


def _fetch_legacy_year(year: int) -> pd.DataFrame:
    df = _download_zip_csv(LEGACY_URL.format(year=year))
    df = _finish(df, LEGACY_COLUMN_MAP)
    df["primary_net"] = df["primary_long"] - df["primary_short"]
    df["secondary_net"] = df["secondary_long"] - df["secondary_short"]
    return df


def _fetch_tff_year(year: int) -> pd.DataFrame:
    df = _download_zip_csv(TFF_URL.format(year=year))
    df.columns = [c.strip() for c in df.columns]
    keep_raw = ["Market_and_Exchange_Names", "As_of_Date_In_Form_YYMMDD",
                "Dealer_Positions_Long_All", "Dealer_Positions_Short_All",
                "Asset_Mgr_Positions_Long_All", "Asset_Mgr_Positions_Short_All",
                "Lev_Money_Positions_Long_All", "Lev_Money_Positions_Short_All"]
    missing = [c for c in keep_raw if c not in df.columns]
    if missing:
        raise RuntimeError(f"missing {missing} after rename; raw_columns_sample={list(df.columns)[:20]}")
    df = df[keep_raw].copy()
    df = df.rename(columns={
        "Market_and_Exchange_Names": "market", "As_of_Date_In_Form_YYMMDD": "date",
    })
    for c in keep_raw[2:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], format="%y%m%d", errors="coerce")
    # institutional/"smart money" side = Dealer + Asset Manager (see module docstring)
    df["primary_net"] = (
        (df["Dealer_Positions_Long_All"] + df["Asset_Mgr_Positions_Long_All"])
        - (df["Dealer_Positions_Short_All"] + df["Asset_Mgr_Positions_Short_All"])
    )
    # speculative/"crowd" side = Leveraged Funds
    df["secondary_net"] = df["Lev_Money_Positions_Long_All"] - df["Lev_Money_Positions_Short_All"]
    return df.dropna(subset=["date"])[["market", "date", "primary_net", "secondary_net"]]


def _fetch_recent_years(fetch_year_fn, report_name: str) -> pd.DataFrame:
    """Current year + previous year, so a 52-week lookback works near January."""
    this_year = datetime.now(timezone.utc).year
    frames = []
    errors = []
    for yr in (this_year - 1, this_year):
        try:
            frames.append(fetch_year_fn(yr))
        except Exception as e:
            detail = f"{yr}: {type(e).__name__}: {e}"
            print(f"[fetch_cot:{report_name}] year failed - {detail}")
            errors.append(detail)
            continue
    if not frames:
        raise RuntimeError(f"Could not fetch any CFTC {report_name} year file | " + " || ".join(errors))
    return pd.concat(frames, ignore_index=True)


def _cot_index(series: pd.Series, lookback: int = 52) -> pd.Series:
    lo = series.rolling(lookback, min_periods=max(4, lookback // 4)).min()
    hi = series.rolling(lookback, min_periods=max(4, lookback // 4)).max()
    return (series - lo) / (hi - lo) * 100


def _resolve_market(df_all: pd.DataFrame, needle: str) -> pd.DataFrame:
    market_lower = df_all["market"].str.lower()
    # startswith, not contains: CFTC market names are "<CONTRACT> - <EXCHANGE>",
    # and `contains` risks silently blending an unrelated market that happens to
    # share a substring into the same net-position series.
    mdf = df_all[market_lower.str.startswith(needle.lower(), na=False)].copy()
    if mdf.empty:
        return mdf
    matched_names = mdf["market"].unique().tolist()
    if len(matched_names) > 1:
        top_name = mdf["market"].value_counts().idxmax()
        mdf = mdf[mdf["market"] == top_name].copy()
    return mdf.sort_values("date").reset_index(drop=True)


def _index_result(mdf: pd.DataFrame, lookback_weeks: int) -> dict:
    if mdf.empty:
        return {"value": "N/A", "date": "N/A", "sentiment": "N/A", "history": []}
    mdf = mdf.copy()
    mdf["cot_index"] = _cot_index(mdf["primary_net"], lookback_weeks)
    mdf["sentiment_index"] = _cot_index(mdf["secondary_net"], lookback_weeks)
    latest = mdf.iloc[-1]
    history = [
        {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 1)}
        for d, v in zip(mdf["date"].tail(30), mdf["cot_index"].tail(30))
        if pd.notna(v)
    ]
    return {
        "value": round(float(latest["cot_index"]), 1) if pd.notna(latest["cot_index"]) else "N/A",
        "sentiment": round(float(latest["sentiment_index"]), 1) if pd.notna(latest["sentiment_index"]) else "N/A",
        "date": latest["date"].strftime("%Y-%m-%d"),
        "history": history,
    }


def get_cot_results(lookback_weeks: int = 52) -> dict:
    cot_cfgs = {iid: cfg for iid, cfg in INDICATORS.items() if cfg.get("source") == "cot"}
    needed_reports = {cfg.get("report", "legacy") for cfg in cot_cfgs.values()}

    dfs = {}
    if "legacy" in needed_reports:
        try:
            dfs["legacy"] = _fetch_recent_years(_fetch_legacy_year, "legacy")
        except Exception as e:
            print(f"[fetch_cot] legacy report unavailable: {e}")
            dfs["legacy"] = None
    if "tff" in needed_reports:
        try:
            dfs["tff"] = _fetch_recent_years(_fetch_tff_year, "tff")
        except Exception as e:
            print(f"[fetch_cot] tff report unavailable: {e}")
            dfs["tff"] = None

    out = {}
    for iid, cfg in cot_cfgs.items():
        report = cfg.get("report", "legacy")
        df_all = dfs.get(report)
        if df_all is None:
            out[iid] = {"value": "N/A", "date": "N/A", "sentiment": "N/A", "history": []}
            continue
        mdf = _resolve_market(df_all, cfg["cot_market"])
        out[iid] = _index_result(mdf, lookback_weeks)
    return out


def main():
    results = get_cot_results()
    (DATA / "cot_cache.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(results)} COT markets to data/cot_cache.json")


if __name__ == "__main__":
    main()
