"""Read bars from CSV files instead of the network (--offline DIR).

Used by tests and by any later back-test: the same calculators run on files.

Layout:  DIR/prices/<TICKER>.csv         columns date,open,high,low,close,volume
         DIR/cftc/<contract code>.csv   columns date,commercial_net,nonreportable_net
"""
from pathlib import Path

import pandas as pd

from . import EMPTY, FAILED, PriceStore, normalize_frame

PRICES_DIR = "prices"
CFTC_DIR = "cftc"
POSITION_COLUMNS = ["commercial_net", "nonreportable_net"]


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


def load_positions(directory, codes):
    """PositionStore built from DIR/cftc/. File names are contract market codes."""
    base = Path(directory) / CFTC_DIR
    store = PriceStore()
    for code in sorted(set(codes)):
        path = base / f"{code}.csv"
        if not path.is_file():
            store.fail(code, FAILED, f"file not found: {path}")
            continue
        try:
            frame = pd.read_csv(path, index_col=0, parse_dates=True)[POSITION_COLUMNS]
            frame = frame.apply(pd.to_numeric, errors="coerce").dropna()
            frame = frame[~frame.index.duplicated(keep="last")].sort_index()
            frame.index.name = "date"
        except Exception as e:  # noqa: BLE001
            store.fail(code, FAILED, f"{type(e).__name__}: {e}")
            continue
        if frame.empty:
            store.fail(code, EMPTY, "no rows")
        else:
            store.put(code, frame)
    return store
