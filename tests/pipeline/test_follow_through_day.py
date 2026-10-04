"""Follow-Through Day state machine (implementation guide 4.4: R1, R2, R3, R7, F1-F4;
F3 as revised by the owner on 2026-10-04).

Hand-made series with small windows so every step can be checked by eye.
Day index:  0-6 rise to the peak (106 on day 6), 7-9 decline, 9 is the low
day (intraday low 97), 10 is Day 1, 13 is Day 4.
"""
import pytest

from pipeline import calc
from pipeline.calc.follow_through_day import replay
from helpers import frame, shipped_indicator

P = {"peak_window": 10, "min_day": 4, "min_gain": 0.0125, "sma_fast": 3, "below_sma_days": 2,
     "vol_avg_window": 5, "fast": 2, "mid": 3, "slow": 5, "slope_window": 1, "events_days": 90}

BASE_CLOSES = [100, 101, 102, 103, 104, 105, 106, 104, 101, 98, 99, 99.5, 99.2, 101.5]
LOW_DAY, DAY1, DAY4 = 9, 10, 13


def series(closes=None, lows=None, volumes=None, extra=()):
    """Base series with optional per-day overrides ({index: value}) and extra closes appended."""
    c = list(BASE_CLOSES) + list(extra)
    for i, v in (closes or {}).items():
        c[i] = v
    lo = [x - 0.5 for x in c]
    lo[LOW_DAY] = 97.0
    for i, v in (lows or {}).items():
        lo[i] = v
    vol = [1000.0] * len(c)
    vol[DAY4] = 1200.0
    for i, v in (volumes or {}).items():
        vol[i] = v
    return frame(c, volumes=vol, lows=lo)


def events(df, params=P):
    return [(e["index"], e["type"], e["day_count"]) for e in replay(df, params)["events"]]


def test_day1_then_ftd_on_day_4():
    out = replay(series(), P)
    assert events(series()) == [(DAY1, "day1", 1), (DAY4, "ftd", 4)]
    assert out["state"] == "CONFIRMED"
    assert out["last_ftd"]["low"] == 101.0 and out["last_ftd"]["day_count"] == 4
    assert out["events"][-1]["gain_pct"] == pytest.approx(2.32, abs=0.01)


def test_strong_day_on_day_3_is_too_early():
    df = series(closes={12: 101.5, 13: 101.6}, volumes={12: 1200, 13: 1000})
    out = replay(df, P)
    assert events(df) == [(DAY1, "day1", 1)]
    assert out["state"] == "WATCHING_RALLY_ATTEMPT" and out["attempt"]["day_count"] == 4


def test_gain_of_exactly_the_threshold_qualifies_and_just_under_does_not():
    assert (DAY4, "ftd", 4) in events(series(closes={12: 100.0, 13: 101.25}))       # +1.25 %
    assert (DAY4, "ftd", 4) not in events(series(closes={12: 100.0, 13: 101.24}))   # +1.24 %


def test_volume_must_exceed_the_previous_day():
    assert (DAY4, "ftd", 4) not in events(series(volumes={13: 1000}))    # equal
    assert (DAY4, "ftd", 4) not in events(series(volumes={13: 999}))     # lower


def test_r2_average_volume_is_a_tag_not_a_condition():
    heavy_before = series(volumes={9: 3000, 10: 3000, 11: 3000, 12: 1000, 13: 1200})
    out = replay(heavy_before, P)                      # 5-day average 2240 > 1200
    assert out["state"] == "CONFIRMED" and out["last_ftd"]["above_avg_volume"] is False
    assert replay(series(), P)["last_ftd"]["above_avg_volume"] is True    # average 1040 < 1200


def test_r1_undercutting_the_rally_low_resets_the_count():
    df = series(lows={12: 96.5})                       # below the rally low of 97 on day 3
    out = replay(df, P)
    # The strong day 13 is now the first higher close after the new low: Day 1, not an FTD.
    assert events(df) == [(DAY1, "day1", 1), (12, "reset", 2), (13, "day1", 1)]
    assert out["attempt"]["rally_low"] == 96.5 and out["attempt"]["day_count"] == 1


def test_r1_a_low_equal_to_the_rally_low_does_not_reset():
    assert events(series(lows={12: 97.0})) == [(DAY1, "day1", 1), (DAY4, "ftd", 4)]


def test_r3_rally_low_is_the_lowest_intraday_low_not_the_lowest_close():
    # Day 8 has the lowest intraday low (96) but day 9 has the lowest close (98).
    df = series(lows={8: 96.0, 9: 97.5, 12: 96.5})
    out = replay(df, P)
    # 96.5 on day 12 would undercut a close-based or day-9 anchor, but not the true low of 96.
    assert events(df) == [(DAY1, "day1", 1), (DAY4, "ftd", 4)]
    assert [e for e in out["events"] if e["type"] == "reset"] == []


def test_f1_no_day1_without_two_closes_below_the_fast_average():
    # Peak 106 on day 6, one down day (103, below its 3-day average), then up.
    df = frame([100, 101, 102, 103, 104, 105, 106, 103, 104, 104.5, 104.2],
               lows=[99.5, 100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 102.0, 103.5, 104.0, 103.7])
    assert events(df) == []


def test_f1_no_day1_when_the_low_day_is_in_a_bullish_trend():
    # Days 7-8 close below the fast average, day 9 is flat, day 10 closes strongly but
    # spikes to the lowest intraday low, day 11 is the first higher close after that low.
    closes = [100, 101, 102, 103, 104, 105, 106, 104.5, 104.4, 104.4, 105.5, 105.6]
    lows = [c - 0.5 for c in closes]
    lows[10] = 95.0
    df = frame(closes, lows=lows)
    bullish_low_day = dict(P, slow=4)                   # day 10: close > fast > mid > slow, mid rising
    assert events(df, bullish_low_day) == []
    assert events(df, P) == [(11, "day1", 1)]           # same prices, low day not bullish: Day 1


def test_f2_new_closing_high_cancels_an_attempt_without_an_ftd():
    df = series(closes={11: 102, 12: 105, 13: 107}, extra=[110], volumes={14: 5000})
    out = replay(df, P)
    assert events(df) == [(DAY1, "day1", 1)]
    assert dict(out["states"])[df.index[13].strftime("%Y-%m-%d")] == "NONE_PENDING"
    assert out["state"] == "NONE_PENDING" and out["attempt"] is None


def test_f3_confirmed_ends_at_a_new_closing_high_and_keeps_the_date():
    df = series(extra=[103, 105, 107])
    result = calc.run({"calculator": "follow_through_day", "inputs": ["subject"], "min_history_days": 5,
                       "params": P, "tone_rule": None}, {"subject": df})
    assert result["state"] == "NONE_PENDING"
    assert result["values"]["last_confirmed_date"] == df.index[DAY4].strftime("%Y-%m-%d")
    assert result["values"]["days_since"] == 3
    assert result["values"]["above_avg_volume"] is True
    assert result["values"]["day_count"] is None


def test_f3_revised_a_new_day1_is_found_while_confirmed():
    # After the FTD: a dip with two closes below the fast average and a higher close after,
    # never closing below the FTD day's low (101.0). The owner's revision of F3 (2026-10-04)
    # lets this start a new attempt; the earlier FTD remains the last confirmed date.
    df = series(extra=[103.5, 102.0, 101.8, 102.6])
    out = replay(df, P)
    assert events(df) == [(DAY1, "day1", 1), (DAY4, "ftd", 4), (17, "day1", 1)]
    assert out["state"] == "WATCHING_RALLY_ATTEMPT"
    assert out["last_ftd"]["index"] == DAY4
    assert dict(out["states"])[df.index[16].strftime("%Y-%m-%d")] == "CONFIRMED"


def test_the_ftd_day_itself_never_starts_a_new_attempt():
    out = replay(series(), P)
    assert out["state"] == "CONFIRMED" and out["attempt"] is None


def test_step4_close_below_the_ftd_low_fails_and_f4_a_new_day1_follows():
    df = series(extra=[102, 100.8, 99.9, 99.0, 99.6])
    out = replay(df, P)
    assert events(df) == [(DAY1, "day1", 1), (DAY4, "ftd", 4), (15, "failed", None), (18, "day1", 1)]
    assert dict(out["states"])[df.index[15].strftime("%Y-%m-%d")] == "FAILED"
    assert out["state"] == "WATCHING_RALLY_ATTEMPT"
    assert out["last_ftd"]["index"] == DAY4            # the failed FTD stays the last confirmed date


def test_close_equal_to_the_ftd_low_does_not_fail():
    df = series(extra=[102, 101.0])
    assert replay(df, P)["state"] == "CONFIRMED"


def test_compute_output_shape_and_tone():
    defn = {"calculator": "follow_through_day", "inputs": ["subject"], "min_history_days": 5, "params": P,
            "tone_rule": shipped_indicator("follow_through_day")["tone_rule"]}
    watching = calc.run(defn, {"subject": series(volumes={13: 1000})})
    assert watching["state"] == "WATCHING_RALLY_ATTEMPT" and watching["tone"] == "warning"
    assert watching["values"] == {"last_confirmed_date": None, "days_since": None, "day_count": 4,
                                  "above_avg_volume": None}
    confirmed = calc.run(defn, {"subject": series()})
    assert confirmed["tone"] == "positive" and confirmed["values"]["days_since"] == 0
    assert confirmed["history"] == []
    assert confirmed["events"] == [
        {"date": "2024-01-16", "type": "day1", "day_count": 1},
        {"date": "2024-01-19", "type": "ftd", "day_count": 4},
    ]
    failed = calc.run(defn, {"subject": series(extra=[102, 100.8])})
    assert failed["state"] == "FAILED" and failed["tone"] == "negative"
    none = calc.run(defn, {"subject": series(extra=[103, 105, 107])})
    assert none["state"] == "NONE_PENDING" and none["tone"] is None


def test_events_are_limited_to_the_recent_window():
    defn = {"calculator": "follow_through_day", "inputs": ["subject"], "min_history_days": 5,
            "params": dict(P, events_days=3), "tone_rule": None}
    result = calc.run(defn, {"subject": series()})
    assert [e["type"] for e in result["events"]] == ["ftd"]         # Day 1 is 4 sessions back


def test_shipped_definition_history_boundary():
    defn = shipped_indicator("follow_through_day")
    need = defn["min_history_days"]
    closes = [100 + i * 0.1 for i in range(need)]
    assert calc.run(defn, {"subject": frame(closes)})["status"] == "ok"
    assert calc.run(defn, {"subject": frame(closes[:-1])})["reason"] == "insufficient_history"
