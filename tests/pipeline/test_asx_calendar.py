"""Finished-bar rules per ticker (spec G.5): an ASX bar is final at 16:30 Sydney time,
an FX bar is never taken on its own day, a ticker without a rule keeps the US rule."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from pipeline import registry
from pipeline.collect import normalize_frame, prices
from helpers import ROOT

SYD = ZoneInfo("Australia/Sydney")
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

UNIVERSE = registry.load_json(ROOT / "config" / "universe.json")
CALENDARS = UNIVERSE["calendars"]


def bars(end, days=5):
    idx = pd.bdate_range(end=end, periods=days)
    return normalize_frame(pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1.0}, index=idx))


# ---- ASX: today is the Sydney date; its bar is final from 16:30 Sydney time

@pytest.mark.parametrize("now,last", [
    (datetime(2026, 10, 9, 10, 30, tzinfo=SYD), "2026-10-08"),   # usual run time (23:30 UTC): session open
    (datetime(2026, 10, 9, 16, 29, tzinfo=SYD), "2026-10-08"),   # closed, not yet 16:30
    (datetime(2026, 10, 9, 16, 30, tzinfo=SYD), "2026-10-09"),   # final
    (datetime(2026, 10, 8, 20, 0, tzinfo=UTC), "2026-10-08"),    # the cron time = 07:00 Sydney on the 9th
])
def test_asx_bar_is_final_at_1630_sydney(now, last):
    out = prices.drop_unfinished(bars("2026-10-09"), now, CALENDARS["asx"])
    assert out.index[-1] == pd.Timestamp(last)


def test_without_the_asx_rule_a_final_asx_bar_would_be_held_back():
    """Why ASX tickers get their own rule: at 17:00 Sydney the day's ASX bar is final, but it
    is 02:00 in New York and the US rule only takes that date's bar after 16:30 Eastern."""
    now = datetime(2026, 10, 9, 17, 0, tzinfo=SYD)
    frame = bars("2026-10-09")
    assert prices.drop_unfinished(frame, now, CALENDARS["asx"]).index[-1] == pd.Timestamp("2026-10-09")
    assert prices.drop_unfinished(frame, now).index[-1] == pd.Timestamp("2026-10-08")


# ---- FX: never today's bar

@pytest.mark.parametrize("now", [
    datetime(2026, 10, 9, 9, 0, tzinfo=ET),
    datetime(2026, 10, 9, 23, 59, tzinfo=ET),
])
def test_fx_never_uses_todays_bar(now):
    out = prices.drop_unfinished(bars("2026-10-09"), now, CALENDARS["fx"])
    assert out.index[-1] == pd.Timestamp("2026-10-08")


# ---- the US rule is unchanged, with or without the explicit calendar

@pytest.mark.parametrize("now", [
    datetime(2026, 10, 9, 16, 29, tzinfo=ET),
    datetime(2026, 10, 9, 16, 30, tzinfo=ET),
    datetime(2026, 10, 9, 23, 30, tzinfo=UTC),
])
def test_us_calendar_equals_the_default_rule(now):
    frame = bars("2026-10-09")
    assert prices.drop_unfinished(frame, now, CALENDARS["us"]).equals(prices.drop_unfinished(frame, now))


def test_fetch_prices_applies_each_tickers_own_rule():
    during_asx_session = datetime(2026, 10, 9, 11, 0, tzinfo=SYD)     # 20:00 Eastern on the 8th
    store = prices.fetch_prices(["AAA", "BBB"], now=during_asx_session, pause=0,
                                batch=lambda t: {k: bars("2026-10-09") for k in t},
                                rules={"BBB": CALENDARS["asx"]})
    assert store.get("AAA").index[-1] == pd.Timestamp("2026-10-08")   # US rule: the 9th is after "today"
    assert store.get("BBB").index[-1] == pd.Timestamp("2026-10-08")   # ASX rule: session still open


def test_registry_and_collector_know_the_same_rule_names():
    assert registry.CALENDAR_RULES == prices.RULES


def test_ticker_rules_cover_every_ticker_meta_entry():
    rules = registry.ticker_rules(UNIVERSE)
    assert set(rules) == set(UNIVERSE["ticker_meta"])
    for ticker, rule in rules.items():
        assert rule is CALENDARS[UNIVERSE["ticker_meta"][ticker]["calendar"]]
