"""
Fetch CFTC Commitments of Traders - "Futures Only" Legacy report
(deacot{year}.zip, Commercial / Non-Commercial / Non-Reportable trader
classification) and compute the COT Index / Sentiment Index (Larry
Williams method, 52-week lookback) for the markets listed in
config.INDICATORS (source == "cot").

Deliberately NOT using the "Financial Futures" (fut_fin_txt / TFF)
report: that one only covers currencies/rates/equity-index markets (no
gold or crude oil) and classifies traders as Dealer/Asset Manager/
Leveraged Money/Other Reportable instead of Commercial/Non-Commercial -
which doesn't match CupSir's "commercial smart money" framework. The
Legacy "Futures Only" report covers every market (financial AND
commodity) in one file with the classification CupSir actually uses.

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

CFTC_URL = "https://www.cftc.gov/files/dea/history/deacot{year}.zip"

COLUMN_MAP = {
    "Market_and_Exchange_Names": "market",
    "As_of_Date_In_Form_YYMMDD": "date",
    "Comm_Positions_Long_All": "comm_long",
    "Comm_Positions_Short_All": "comm_short",
    "NonComm_Positions_Long_All": "large_spec_long",
    "NonComm_Positions_Short_All": "large_spec_short",
    "NonRept_Positions_Long_All": "small_spec_long",
    "NonRept_Positions_Short_All": "small_spec_short",
}


HEADERS = {
    # cftc.gov returns 403 to requests' default User-Agent on some networks
    # (including GitHub Actions runners) - a browser-like UA fixes it.
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/zip,application/octet-stream,*/*",
}


def _fetch_year(year: int) -> pd.DataFrame:
    url = CFTC_URL.format(year=year)
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
    df = df.rename(columns=COLUMN_MAP)
    keep = list(COLUMN_MAP.values())
    missing = [c for c in keep if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"missing {missing} after rename; zip={names[:5]}; picked={filename}; "
            f"raw_columns_sample={list(df.columns)[:20]}"
        )
    df = df[[c for c in keep if c in df.columns]].copy()
    for c in ["comm_long", "comm_short", "large_spec_long", "large_spec_short", "small_spec_long", "small_spec_short"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["comm_net"] = df["comm_long"] - df["comm_short"]
    df["large_spec_net"] = df["large_spec_long"] - df["large_spec_short"]
    df["small_spec_net"] = df["small_spec_long"] - df["small_spec_short"]
    df["date"] = pd.to_datetime(df["date"], format="%y%m%d", errors="coerce")
    return df.dropna(subset=["date"])


def _fetch_recent_years() -> pd.DataFrame:
    """Current year + previous year, so a 52-week lookback works near January."""
    this_year = datetime.now(timezone.utc).year
    frames = []
    errors = []
    for yr in (this_year - 1, this_year):
        try:
            frames.append(_fetch_year(yr))
        except Exception as e:
            detail = f"{yr}: {type(e).__name__}: {e}"
            print(f"[fetch_cot] year failed - {detail}")
            errors.append(detail)
            continue
    if not frames:
        raise RuntimeError("Could not fetch any CFTC COT year file | " + " || ".join(errors))
    return pd.concat(frames, ignore_index=True)


def _cot_index(series: pd.Series, lookback: int = 52) -> pd.Series:
    lo = series.rolling(lookback, min_periods=max(4, lookback // 4)).min()
    hi = series.rolling(lookback, min_periods=max(4, lookback // 4)).max()
    return (series - lo) / (hi - lo) * 100


def get_cot_results(lookback_weeks: int = 52) -> dict:
    df_all = _fetch_recent_years()
    out = {}
    for iid, cfg in INDICATORS.items():
        if cfg.get("source") != "cot":
            continue
        needle = cfg["cot_market"].lower()
        market_lower = df_all["market"].str.lower()
        # startswith, not contains: CFTC market names are "<CONTRACT> - <EXCHANGE>",
        # and `contains` risks silently blending rows from an unrelated market that
        # happens to share a substring (e.g. "GOLD" also appearing inside some other
        # contract's name) into the same net-position series.
        mdf = df_all[market_lower.str.startswith(needle, na=False)].copy()
        if mdf.empty:
            out[iid] = {"value": "N/A", "date": "N/A", "sentiment": "N/A", "history": [],
                        "_debug_no_match": needle}
            continue
        matched_names = mdf["market"].unique().tolist()
        if len(matched_names) > 1:
            # Multiple distinct market listings matched (e.g. different contract
            # months/exchanges) - keep only the most frequent one so the net-position
            # series stays internally consistent.
            top_name = mdf["market"].value_counts().idxmax()
            mdf = mdf[mdf["market"] == top_name].copy()
        mdf = mdf.sort_values("date").reset_index(drop=True)
        mdf["cot_index"] = _cot_index(mdf["comm_net"], lookback_weeks)
        mdf["sentiment_index"] = _cot_index(mdf["small_spec_net"], lookback_weeks)
        latest = mdf.iloc[-1]
        history = [
            {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 1)}
            for d, v in zip(mdf["date"].tail(30), mdf["cot_index"].tail(30))
            if pd.notna(v)
        ]
        out[iid] = {
            "value": round(float(latest["cot_index"]), 1) if pd.notna(latest["cot_index"]) else "N/A",
            "sentiment": round(float(latest["sentiment_index"]), 1) if pd.notna(latest["sentiment_index"]) else "N/A",
            "date": latest["date"].strftime("%Y-%m-%d"),
            "history": history,
        }
    return out


def main():
    results = get_cot_results()
    (DATA / "cot_cache.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(results)} COT markets to data/cot_cache.json")


if __name__ == "__main__":
    main()
