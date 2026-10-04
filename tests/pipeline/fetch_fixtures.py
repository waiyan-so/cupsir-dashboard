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


def main():
    requests_ = json.loads(REQUEST.read_text(encoding="utf-8"))["requests"]
    OUT.mkdir(parents=True, exist_ok=True)
    failed = 0
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
