"""Daily bars from Yahoo Finance (yfinance), adjusted for splits and dividends.

Why adjusted prices: sector ETFs pay dividends every quarter. On unadjusted
closes the ex-dividend day shows an extra fall big enough to pass the
distribution-day threshold and create a false signal.

Why today's bar is dropped until the session has ended: the workflow can run
while the US market is still open. A half-finished bar has incomplete volume,
which breaks every "volume higher than yesterday" test.
"""
import time
from datetime import datetime, time as clock
from zoneinfo import ZoneInfo

import pandas as pd

from . import EMPTY, FAILED, PriceStore, normalize_frame

MARKET_TZ = ZoneInfo("America/New_York")
BAR_FINAL_AFTER = clock(16, 30)     # US Eastern; the session closes at 16:00
LOOKBACK = "2y"                     # every ticker; min_history_days only decides N/A
RETRIES = 2                         # extra attempts after the first failure
RETRY_PAUSE_SECONDS = 2


def drop_unfinished(frame, now):
    """Keep bars dated before today (US Eastern). Keep today's bar only when
    `now` is at or after 16:30 Eastern. `now` must be timezone-aware."""
    now_et = now.astimezone(MARKET_TZ)
    today = pd.Timestamp(now_et.date())
    if now_et.time() >= BAR_FINAL_AFTER:
        return frame[frame.index <= today]
    return frame[frame.index < today]


def _yahoo_batch(tickers):
    """One request for all tickers. Returns {ticker: raw table}."""
    import yfinance as yf
    raw = yf.download(tickers, period=LOOKBACK, interval="1d", auto_adjust=True,
                      group_by="ticker", threads=True, progress=False)
    return split_batch(raw, tickers)


def split_batch(raw, tickers):
    """Split a multi-ticker download (columns = ticker x field) into one table per ticker.
    A ticker that is absent, or whose rows are all empty, maps to None."""
    out = {}
    for ticker in tickers:
        try:
            part = raw[ticker] if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            part = None
        if part is not None and part.dropna(how="all").empty:
            part = None
        out[ticker] = part
    return out


def _yahoo_single(ticker):
    import yfinance as yf
    return yf.Ticker(ticker).history(period=LOOKBACK, interval="1d", auto_adjust=True)


def fetch_prices(tickers, now=None, batch=None, single=None, pause=RETRY_PAUSE_SECONDS):
    """Fetch every ticker once and return a PriceStore.

    One failing ticker never affects the others. A ticker that fails or comes
    back empty in the batch request is retried on its own up to RETRIES times.
    `now`, `batch` and `single` exist so tests can run without a network.
    """
    now = now or datetime.now(MARKET_TZ)
    batch = batch or _yahoo_batch
    single = single or _yahoo_single
    tickers = sorted(set(tickers))
    store = PriceStore()

    try:
        raw_by_ticker = batch(tickers)
    except Exception as e:  # noqa: BLE001 - fall back to one-by-one
        print(f"[collect] batch download failed, fetching one by one: {type(e).__name__}: {e}")
        raw_by_ticker = {}

    for ticker in tickers:
        frame, error = _clean(raw_by_ticker.get(ticker), now)
        attempt = 0
        while frame is None and attempt < RETRIES:
            attempt += 1
            if pause:
                time.sleep(pause)
            try:
                frame, error = _clean(single(ticker), now)
            except Exception as e:  # noqa: BLE001
                frame, error = None, (FAILED, f"{type(e).__name__}: {e}")
        if frame is None:
            store.fail(ticker, *error)
        else:
            store.put(ticker, frame)
    return store


def _clean(raw, now):
    """(frame, None) when usable, otherwise (None, (status, message))."""
    if raw is None:
        return None, (FAILED, "no data returned")
    try:
        frame = drop_unfinished(normalize_frame(raw), now)
    except Exception as e:  # noqa: BLE001
        return None, (FAILED, f"{type(e).__name__}: {e}")
    if frame.empty:
        return None, (EMPTY, "no finished daily bars")
    return frame, None
