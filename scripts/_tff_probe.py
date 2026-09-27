"""
TEMPORARY one-shot diagnostic script - NOT part of the pipeline.

Downloads the real "Traders in Financial Futures" (TFF) report
(fut_fin_txt_{year}.zip) and writes the real column names + candidate
market-name rows for S&P 500 / 10-Year Treasury / US Dollar Index into
data/tff_probe.json, so the real ground truth can be read via
raw.githubusercontent.com instead of guessing again. Delete this file
and its update-data.yml step once fetch_cot.py's TFF path is confirmed
working.
"""
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

URL = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/zip,application/octet-stream,*/*",
}


def probe_year(year: int) -> dict:
    r = requests.get(URL.format(year=year), headers=HEADERS, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = z.namelist()
        txt_names = [f for f in names if f.lower().endswith(".txt")]
        filename = txt_names[0] if txt_names else names[0]
        with z.open(filename) as f:
            df = pd.read_csv(f, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    market_col_candidates = [c for c in df.columns if "market" in c.lower() and "exchange" in c.lower()]
    market_col = market_col_candidates[0] if market_col_candidates else df.columns[0]
    markets = df[market_col].astype(str).str.strip()

    def find(keyword: str):
        return sorted(markets[markets.str.lower().str.contains(keyword, na=False)].unique().tolist())[:10]

    return {
        "zip_namelist": names,
        "picked_file": filename,
        "columns": list(df.columns),
        "market_column_used": market_col,
        "row_count": len(df),
        "sp500_candidates": find("s&p 500"),
        "treasury_10y_candidates": sorted(set(find("10-year") + find("10 year") + find("10-yr") + find("treasury") + find("ust 10") + find("note"))),
        "dollar_index_candidates": find("dollar index") + find("usd index"),
    }


def main():
    out = {"probed_at": datetime.now(timezone.utc).isoformat()}
    this_year = datetime.now(timezone.utc).year
    for yr in (this_year, this_year - 1):
        try:
            out[str(yr)] = probe_year(yr)
            break  # one good year is enough for a column/name probe
        except Exception as e:
            out[str(yr)] = {"error": f"{type(e).__name__}: {e}"}
    (DATA / "tff_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote data/tff_probe.json")


if __name__ == "__main__":
    main()
