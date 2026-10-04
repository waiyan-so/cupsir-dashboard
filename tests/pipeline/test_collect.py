"""Collection layer (spec A.5 a): frame shape, unfinished-bar rule, isolation, retries, CSV input."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from pipeline.collect import COLUMNS, normalize_frame
from pipeline.collect import fixtures, prices

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def raw(days, tz=None, start="2026-01-05"):
    """What a download looks like: capitalised columns, optionally a timezone-aware index."""
    idx = pd.bdate_range(start=start, periods=days, tz=tz)
    return pd.DataFrame({"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 100.0,
                         "Dividends": 0.0}, index=idx)


# ---- PriceFrame shape

def test_normalize_gives_the_priceframe_shape():
    df = raw(5, tz="America/New_York")
    df.iloc[2, df.columns.get_loc("Close")] = float("nan")       # a row with a gap is dropped
    out = normalize_frame(df.iloc[::-1])                          # given newest first
    assert list(out.columns) == COLUMNS
    assert out.index.tz is None and out.index.is_monotonic_increasing
    assert len(out) == 4 and not out.isna().any().any()


def test_normalize_rejects_a_table_without_volume():
    with pytest.raises(ValueError):
        normalize_frame(raw(3).drop(columns=["Volume"]))


# ---- unfinished bar (the bar dated "today" in US Eastern time)

TODAY = "2026-01-09"       # a Friday; raw(5) ends on this date


@pytest.mark.parametrize("now,kept", [
    (datetime(2026, 1, 9, 15, 59, tzinfo=ET), False),    # market still open
    (datetime(2026, 1, 9, 16, 29, tzinfo=ET), False),    # closed, but before 16:30
    (datetime(2026, 1, 9, 16, 30, tzinfo=ET), True),     # exactly 16:30
    (datetime(2026, 1, 9, 20, 0, tzinfo=UTC), False),    # the cron time in winter = 15:00 Eastern
    (datetime(2026, 1, 9, 23, 25, tzinfo=UTC), True),    # a delayed run = 18:25 Eastern
    (datetime(2026, 1, 10, 3, 0, tzinfo=UTC), True),     # still 22:00 Eastern on the 9th
    (datetime(2026, 1, 10, 9, 0, tzinfo=ET), True),      # next morning
])
def test_todays_bar_is_kept_only_after_1630_eastern(now, kept):
    out = prices.drop_unfinished(normalize_frame(raw(5)), now)
    assert (out.index[-1] == pd.Timestamp(TODAY)) is kept
    assert len(out) == (5 if kept else 4)


def test_summer_cron_time_is_also_before_the_cutoff():
    frame = normalize_frame(raw(5, start="2026-07-06"))                     # ends Friday 2026-07-10
    out = prices.drop_unfinished(frame, datetime(2026, 7, 10, 20, 0, tzinfo=UTC))   # 16:00 Eastern
    assert out.index[-1] == pd.Timestamp("2026-07-09")


# ---- fetch_prices: isolation, retries, de-duplication

AFTER_CLOSE = datetime(2026, 1, 9, 18, 0, tzinfo=ET)


def test_one_failing_ticker_does_not_affect_the_others_and_is_retried_twice():
    calls = []

    def batch(tickers):
        return {t: (None if t == "BAD" else raw(5)) for t in tickers}

    def single(ticker):
        calls.append(ticker)
        raise ConnectionError("no route")

    store = prices.fetch_prices(["AAA", "BAD", "AAA"], now=AFTER_CLOSE, batch=batch, single=single, pause=0)
    assert store.status == {"AAA": "ok", "BAD": "failed"}
    assert calls == ["BAD", "BAD"]                       # two retries, and AAA fetched only once
    assert store.get("BAD") is None and "no route" in store.errors["BAD"]
    assert len(store.get("AAA")) == 5


def test_a_retry_can_recover_a_ticker():
    attempts = {"n": 0}

    def single(ticker):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise TimeoutError("slow")
        return raw(5)

    store = prices.fetch_prices(["AAA"], now=AFTER_CLOSE, batch=lambda t: {}, single=single, pause=0)
    assert store.status == {"AAA": "ok"} and attempts["n"] == 2


def test_batch_failure_falls_back_to_single_requests():
    def batch(tickers):
        raise RuntimeError("batch endpoint down")

    store = prices.fetch_prices(["AAA", "BBB"], now=AFTER_CLOSE, batch=batch, single=lambda t: raw(5), pause=0)
    assert store.status == {"AAA": "ok", "BBB": "ok"}


def test_empty_download_is_reported_as_empty():
    store = prices.fetch_prices(["AAA"], now=AFTER_CLOSE, batch=lambda t: {"AAA": raw(0)},
                                single=lambda t: raw(0), pause=0)
    assert store.status == {"AAA": "empty"} and store.get("AAA") is None


def test_unfinished_bar_is_removed_inside_fetch_prices():
    during_session = datetime(2026, 1, 9, 12, 0, tzinfo=ET)
    store = prices.fetch_prices(["AAA"], now=during_session, batch=lambda t: {"AAA": raw(5)}, pause=0)
    assert store.get("AAA").index[-1] == pd.Timestamp("2026-01-08")


def test_yahoo_requests_ask_for_adjusted_prices():
    import inspect
    assert "auto_adjust=True" in inspect.getsource(prices._yahoo_batch)
    assert "auto_adjust=True" in inspect.getsource(prices._yahoo_single)


# ---- CSV input (--offline)

def test_load_prices_from_csv_directory(tmp_path):
    folder = tmp_path / "prices"
    folder.mkdir()
    normalize_frame(raw(5)).to_csv(folder / "AAA.csv")
    (folder / "EMPTY.csv").write_text("date,open,high,low,close,volume\n", encoding="utf-8")
    store = fixtures.load_prices(tmp_path, ["AAA", "MISSING", "EMPTY"])
    assert store.status == {"AAA": "ok", "MISSING": "failed", "EMPTY": "empty"}
    assert list(store.get("AAA").columns) == COLUMNS and len(store.get("AAA")) == 5
    assert "file not found" in store.errors["MISSING"]


def test_real_fixture_loads_as_a_priceframe():
    from helpers import ROOT
    frame = fixtures.load_csv(ROOT / "tests/pipeline/fixtures/real/SPY_2019-01-02_2020-07-01.csv")
    assert list(frame.columns) == COLUMNS and len(frame) == 377 and frame.index.tz is None
