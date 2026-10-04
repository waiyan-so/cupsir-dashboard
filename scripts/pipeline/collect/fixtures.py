"""Read bars from CSV files instead of the network (--offline DIR).

Used by tests and by any later back-test: the same calculators run on files.

Layout:  DIR/prices/<TICKER>.csv   columns date,open,high,low,close,volume
"""
from pathlib import Path

import pandas as pd

from . import EMPTY, FAILED, PriceStore, normalize_frame

PRICES_DIR = "prices"


def load_csv(path):
    return normalize_frame(pd.read_csv(path, index_col=0, parse_dates=True))


def load_prices(directory, tickers):
    """PriceStore built from DIR/prices/. A missing or unreadable file is a failed ticker."""
    base = Path(directory) / PRICES_DIR
    store = PriceStore()
    for ticker in sorted(set(tickers)):
        path = base / f"{ticker}.csv"
        if not path.is_file():
            store.fail(ticker, FAILED, f"file not found: {path}")
            continue
        try:
            frame = load_csv(path)
        except Exception as e:  # noqa: BLE001
            store.fail(ticker, FAILED, f"{type(e).__name__}: {e}")
            continue
        if frame.empty:
            store.fail(ticker, EMPTY, "no rows")
        else:
            store.put(ticker, frame)
    return store
