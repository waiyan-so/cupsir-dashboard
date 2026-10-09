"""Daily bars from Yahoo Finance (yfinance), adjusted for splits and dividends.

Why adjusted prices: sector ETFs pay dividends every quarter. On unadjusted
closes the ex-dividend day shows an extra fall big enough to pass the
distribution-day threshold and create a false signal.

Why today's bar is dropped until the session has ended: the workflow can run
while the US market is still open. A half-finished bar has incomplete volume,
which breaks every "volume higher than yesterday" test.

Which day counts as "today", and when its bar is final, depends on where the
ticker trades (spec G.5). The orchestrator hands in one rule per ticker, read
from config; a ticker without one uses the US Eastern rule below. This layer
does not know which scope or market a ticker belongs to.

    {"tz": "...", "rule": "session_close", "final_after": "HH:MM"}
        bars before today (in tz); today's bar too once the local time is at or after final_after
    {"tz": "...", "rule": "previous_day"}
        bars before today (in tz) only, whatever the time
"""
import time
from datetime import datetime, time as clock
from zoneinfo import ZoneInfo

import pandas as pd

from . import EMPTY, FAILED, PriceStore, normalize_frame

MARKET_TZ = ZoneInfo("America/New_York")
LOOKBACK = "2y"                     # every ticker; min_history_days only decides N/A
RETRIES = 2                         # extra attempts after the first failure
RETRY_PAUSE_SECONDS = 2


SESSION_CLOSE = "session_close"
PREVIOUS_DAY = "previous_day"
RULES = (SESSION_CLOSE, PREVIOUS_DAY)
DEFAULT_RULE = {"tz": "America/New_York", "rule": SESSION_CLOSE, "final_after": "16:30"}


def _clock(text):
    hours, minutes = text.split(":")
    return clock(int(hours), int(minutes))


def drop_unfinished(frame, now, rule=None):
    """Keep bars dated before today; keep today's bar only once it is final.
    Without `rule`: today is the US Eastern date and its bar is final at 16:30
    Eastern. `now` must be timezone-aware."""
    rule = rule or DEFAULT_RULE
    local = now.astimezone(ZoneInfo(rule["tz"]))
    today = pd.Timestamp(local.date())
    if rule["rule"] == SESSION_CLOSE and local.time() >= _clock(rule["final_after"]):
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


def fetch_prices(tickers, now=None, batch=None, single=None, pause=RETRY_PAUSE_SECONDS, rules=None):
    """Fetch every ticker once and return a PriceStore.

    One failing ticker never affects the others. A ticker that fails or comes
    back empty in the batch request is retried on its own up to RETRIES times.
    `rules`: {ticker: finished-bar rule}; tickers not in it use DEFAULT_RULE.
    `now`, `batch` and `single` exist so tests can run without a network.
    """
    rules = rules or {}
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
        rule = rules.get(ticker)
        frame, error = _clean(raw_by_ticker.get(ticker), now, rule)
        attempt = 0
        while frame is None and attempt < RETRIES:
            attempt += 1
            if pause:
                time.sleep(pause)
            try:
                frame, error = _clean(single(ticker), now, rule)
            except Exception as e:  # noqa: BLE001
                frame, error = None, (FAILED, f"{type(e).__name__}: {e}")
        if frame is None:
            store.fail(ticker, *error)
        else:
            store.put(ticker, frame)
    return store


def _clean(raw, now, rule=None):
    """(frame, None) when usable, otherwise (None, (status, message))."""
    if raw is None:
        return None, (FAILED, "no data returned")
    try:
        frame = drop_unfinished(normalize_frame(raw), now, rule)
    except Exception as e:  # noqa: BLE001
        return None, (FAILED, f"{type(e).__name__}: {e}")
    if frame.empty:
        return None, (EMPTY, "no finished daily bars")
    return frame, None
