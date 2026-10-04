"""
Download the daily bars listed in tests/pipeline/fixtures/request.json and
save them as CSV test fixtures (tests/pipeline/fixtures/real/).

This is a test helper, not part of the daily pipeline. It runs on GitHub
Actions (workflow "Fetch test fixtures") because that is where Yahoo Finance
is reachable. The daily pipeline never commits raw prices; these files are
small, fixed historical windows that the fixed tests need.

File name: <TICKER>_<start>_<end>[_raw].csv   (_raw = auto_adjust false)
Columns:   date,open,high,low,close,volume
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
REQUEST = HERE / "fixtures" / "request.json"
OUT = HERE / "fixtures" / "real"
COLUMNS = ["open", "high", "low", "close", "volume"]
RETRIES = 3


def fixture_name(req):
    suffix = "" if req.get("auto_adjust", True) else "_raw"
    return f"{req['ticker']}_{req['start']}_{req['end']}{suffix}.csv"


def fetch(req):
    last_error = None
    for attempt in range(RETRIES):
        try:
            df = yf.Ticker(req["ticker"]).history(
                start=req["start"], end=req["end"], interval="1d",
                auto_adjust=req.get("auto_adjust", True), actions=False)
            if df is not None and not df.empty:
                df = df.rename(columns=str.lower)[COLUMNS].dropna()
                df.index = df.index.tz_localize(None).normalize()
                df.index.name = "date"
                return df
            last_error = "empty result"
        except Exception as e:  # noqa: BLE001 - report and retry
            last_error = f"{type(e).__name__}: {e}"
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(last_error)


def fetch_cftc(spec):
    """Rows of the real CFTC yearly files for a few contract codes, kept in the files' own
    column layout so tests exercise the production parser. Also records the full header."""
    sys.path.insert(0, str(HERE.parents[1] / "scripts"))
    from pipeline.collect import cftc
    tables = [cftc.download_year(year) for year in spec["years"]]
    raw = pd.concat(tables, ignore_index=True)
    (OUT / "cftc_legacy_header.txt").write_text("\n".join(str(c) for c in tables[-1].columns) + "\n", encoding="utf-8")
    code_col = cftc.find_column(raw, cftc.CODE_COLUMN)
    keep = [cftc.find_column(raw, cftc.NAME_COLUMN), cftc.find_column(raw, cftc.DATE_COLUMN), code_col]
    keep += [cftc.find_column(raw, name) for name in cftc.POSITION_COLUMNS.values()]
    sample = raw[raw[code_col].astype(str).str.strip().isin(spec["codes"])][keep]
    sample.to_csv(OUT / "cftc_legacy_sample.csv", index=False)
    print(f"cftc_legacy_sample.csv: {len(sample)} rows, code column is '{code_col}', "
          f"codes found: {sorted(sample[code_col].astype(str).str.strip().unique())}")


def main():
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    requests_ = request["requests"]
    OUT.mkdir(parents=True, exist_ok=True)
    failed = 0
    if "cftc" in request:
        try:
            fetch_cftc(request["cftc"])
        except Exception as e:  # noqa: BLE001
            failed += 1
            (OUT / "cftc_legacy_error.txt").write_text(f"{type(e).__name__}: {e}\n", encoding="utf-8")
            print(f"::warning::cftc sample: download failed - {type(e).__name__}: {e}")
    for req in requests_:
        name = fixture_name(req)
        try:
            df = fetch(req)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"::warning::{name}: download failed - {e}")
            continue
        df.to_csv(OUT / name, float_format="%.6f")
        print(f"{name}: {len(df)} rows, {df.index[0].date()} to {df.index[-1].date()}, "
              f"volume column ok = {bool((df['volume'] > 0).all())}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
