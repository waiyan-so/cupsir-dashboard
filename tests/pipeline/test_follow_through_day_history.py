"""
Fixed tests on real SPY / QQQ bars: the three documented cases of spec section 8.

Expected dates come from reports about the indexes (S&P 500, Nasdaq), not the
ETFs. Two of the five expectations do NOT hold on ETF data with the approved
formula. They are marked xfail(strict) and each has a companion test that
pins down the reason, so the difference stays visible and is never papered
over by changing a threshold:

  SPY 2020-04-02  gain and day count qualify, but SPY's volume was lower than
                  the day before. The formula confirms on 2020-04-06 instead.
  SPY 2023-01-06  the day itself qualifies on gain and volume, but SPY was
                  still CONFIRMED from its 2022-10-21 FTD (never closed below
                  that day's low, never made a 63-day closing high), and
                  default F3 does not look for a new Day 1 while CONFIRMED.
"""
import pytest

from pipeline.calc.follow_through_day import replay
from helpers import real_fixture, shipped_indicator

PARAMS = shipped_indicator("follow_through_day")["params"]

SPY_2020 = "SPY_2019-01-02_2020-07-01.csv"
QQQ_2020 = "QQQ_2019-01-02_2020-07-01.csv"
SPY_2023 = "SPY_2021-07-01_2024-01-01.csv"
QQQ_2023 = "QQQ_2021-07-01_2024-01-01.csv"


def _replay(name):
    df = real_fixture(name)
    return df, replay(df, PARAMS)


def _on(out, date):
    return [(e["type"], e["day_count"]) for e in out["events"] if e["date"] == date]


def _ftd_dates(out):
    return [e["date"] for e in out["events"] if e["type"] == "ftd"]


# ---- case 1: March-April 2020

def test_spy_2020_day1_is_03_24():
    _, out = _replay(SPY_2020)
    assert _on(out, "2020-03-24") == [("day1", 1)]
    assert _on(out, "2020-03-23") == [("reset", 2)]       # the 03-23 low undercut the previous attempt


@pytest.mark.xfail(strict=True, reason="SPY volume on 2020-04-02 was lower than on 04-01; see the next test")
def test_spy_2020_ftd_is_04_02():
    _, out = _replay(SPY_2020)
    assert "2020-04-02" in _ftd_dates(out)


def test_spy_2020_04_02_misses_only_on_volume_and_confirms_on_04_06():
    df, out = _replay(SPY_2020)
    gain = df.loc["2020-04-02", "close"] / df.loc["2020-04-01", "close"] - 1
    assert gain >= PARAMS["min_gain"]                                         # +2.31 %
    assert df.loc["2020-04-02", "volume"] < df.loc["2020-04-01", "volume"]    # the failing condition
    assert _ftd_dates(out) == ["2020-04-06"]
    assert _on(out, "2020-04-06") == [("ftd", 10)]


def test_qqq_2020_ftd_is_04_02_on_day_8_below_average_volume():
    _, out = _replay(QQQ_2020)
    assert _on(out, "2020-03-24") == [("day1", 1)]
    assert _on(out, "2020-04-02") == [("ftd", 8)]
    ftd = [e for e in out["events"] if e["type"] == "ftd"][0]
    assert ftd["above_avg_volume"] is False               # R2: would have been missed as a hard condition


# ---- case 2: 2023-01-06

def test_qqq_2023_01_06_is_an_ftd():
    _, out = _replay(QQQ_2023)
    assert _on(out, "2022-12-29") == [("day1", 1)]
    assert _on(out, "2023-01-06") == [("ftd", 6)]


@pytest.mark.xfail(strict=True, reason="SPY was still CONFIRMED from 2022-10-21 (default F3); see the next test")
def test_spy_2023_01_06_is_an_ftd():
    _, out = _replay(SPY_2023)
    assert "2023-01-06" in _ftd_dates(out)


def test_spy_2023_01_06_qualifies_on_the_day_but_state_was_still_confirmed():
    df, out = _replay(SPY_2023)
    gain = df.loc["2023-01-06", "close"] / df.loc["2023-01-05", "close"] - 1
    assert gain >= PARAMS["min_gain"]                                         # +2.29 %
    assert df.loc["2023-01-06", "volume"] > df.loc["2023-01-05", "volume"]
    states = dict(out["states"])
    assert _on(out, "2022-10-21") == [("ftd", 5)]
    assert all(states[d.strftime("%Y-%m-%d")] == "CONFIRMED"
               for d in df.loc["2022-10-21":"2023-01-06"].index)
    assert [e for e in out["events"] if "2022-10-22" <= e["date"] <= "2023-01-06"] == []


# ---- case 3: 2023-11-01

def test_qqq_2023_11_01_is_an_ftd_on_day_4():
    _, out = _replay(QQQ_2023)
    assert _on(out, "2023-10-27") == [("day1", 1)]
    assert _on(out, "2023-11-01") == [("ftd", 4)]


def test_spy_2023_11_01_is_not_an_ftd():
    _, out = _replay(SPY_2023)
    assert _on(out, "2023-11-01") == []
    assert _on(out, "2023-11-10") == [("ftd", 10)]        # SPY confirms later


# ---- the failure rule on real data (spec 3.4.2 had no case for it)

def test_failed_ftds_of_2022_are_detected():
    _, out = _replay(QQQ_2023)
    failed = [e["date"] for e in out["events"] if e["type"] == "failed"]
    assert failed[:3] == ["2022-06-09", "2022-06-28", "2022-11-02"]
