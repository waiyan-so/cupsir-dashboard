"""Ratio Trend (spec F.3). Small windows make the arithmetic checkable by hand."""
import pandas as pd
import pytest

from pipeline import calc
from pipeline.calc._math import sig
from pipeline.calc.ratio_trend import compute
from helpers import frame, shipped_indicator

SMALL = {"fast": 2, "mid": 3, "slow": 5, "slope_window": 1, "short_window": 2, "long_window": 4, "history_days": 3}


def _ratio_frames(ratios, start="2024-01-02"):
    """subject / benchmark equals `ratios`: the benchmark is a constant 2, the subject twice the ratio."""
    return {"subject": frame([2 * r for r in ratios], start=start), "benchmark": frame([2.0] * len(ratios), start=start)}


def test_rising_ratio():
    # ratio 7 > fast 6.5 > mid 6 > slow 5, mid slope +1
    out = compute(_ratio_frames([1, 2, 3, 4, 5, 6, 7]), SMALL)
    assert out["state"] == "RISING"
    assert out["values"]["ratio"] == 7 and out["values"]["sma2"] == 6.5
    assert out["values"]["sma3"] == 6 and out["values"]["sma5"] == 5
    assert out["values"]["sma3_rising"] is True


def test_falling_ratio():
    # ratio 5 < mid 6, 5 < slow 7, mid slope -1
    assert compute(_ratio_frames([10, 9, 8, 7, 6, 5]), SMALL)["state"] == "FALLING"


def test_flat_ratio_is_mixed():
    out = compute(_ratio_frames([5] * 7), SMALL)
    assert out["state"] == "MIXED" and out["values"]["sma3_rising"] is False


def test_changes_and_distance_from_the_averages():
    out = compute(_ratio_frames([1, 2, 3, 4, 5, 6, 7]), SMALL)
    v = out["values"]
    assert v["change_2d_pct"] == pytest.approx((7 / 5 - 1) * 100, abs=0.005)    # ratio 2 days ago = 5
    assert v["change_4d_pct"] == pytest.approx((7 / 3 - 1) * 100, abs=0.005)    # 4 days ago = 3
    assert v["vs_sma3_pct"] == pytest.approx((7 / 6 - 1) * 100, abs=0.005)
    assert v["vs_sma5_pct"] == pytest.approx((7 / 5 - 1) * 100, abs=0.005)


def test_the_ratio_is_subject_over_benchmark_not_the_other_way():
    frames = {"subject": frame([10.0] * 7), "benchmark": frame([4.0] * 7)}
    assert compute(frames, SMALL)["values"]["ratio"] == 2.5


def test_history_holds_the_ratio_and_two_averages_for_the_last_days():
    out = compute(_ratio_frames([1, 2, 3, 4, 5, 6, 7]), SMALL)
    assert [set(p) for p in out["history"]] == [{"date", "ratio", "sma3", "sma5"}] * 3
    assert [p["ratio"] for p in out["history"]] == [5, 6, 7]
    assert out["history"][-1]["date"] == str(frame([0] * 7).index[-1].date())


def test_no_history_when_history_days_is_zero():
    assert compute(_ratio_frames([1, 2, 3, 4, 5, 6, 7]), dict(SMALL, history_days=0))["history"] == []


def test_a_tiny_ratio_keeps_six_significant_figures():
    # copper / gold is about 0.0016: fixed decimals would leave two digits
    frames = {"subject": frame([4.567891] * 7), "benchmark": frame([2876.54321] * 7)}
    ratio = compute(frames, SMALL)["values"]["ratio"]
    assert ratio == sig(4.567891 / 2876.54321, 6)
    assert len(f"{ratio:.12g}".replace("0.", "").lstrip("0")) == 6


def test_sig():
    assert sig(0.001587962, 3) == 0.00159
    assert sig(1234.5678, 6) == 1234.57
    assert sig(-0.5, 2) == -0.5
    assert sig(0, 6) == 0.0
    assert sig(float("nan"), 6) is None and sig(None, 6) is None


def test_dates_are_aligned_before_dividing():
    """Two series that do not trade on the same days: only shared dates are used (calc.run)."""
    defn = dict(shipped_indicator("pair_trend"), min_history_days=6, params=dict(SMALL, history_days=20))
    subject = frame([2, 4, 6, 8, 10, 12, 14, 16])
    benchmark = frame([2.0] * 8).drop(subject.index[3])       # the benchmark misses one day
    result = calc.run(defn, {"subject": subject, "benchmark": benchmark})
    assert result["status"] == "ok"
    dates = [p["date"] for p in result["history"]]
    assert len(dates) == 7 and str(subject.index[3].date()) not in dates
    assert result["values"]["ratio"] == 8      # 16 / 2 on the last shared day


def test_shipped_definition_gives_na_when_history_is_short():
    defn = shipped_indicator("pair_trend")
    short = _ratio_frames([1 + i / 100 for i in range(defn["min_history_days"] - 1)])
    assert calc.run(defn, short)["reason"] == "insufficient_history"
    enough = _ratio_frames([1 + i / 100 for i in range(defn["min_history_days"])])
    result = calc.run(defn, enough)
    assert result["status"] == "ok" and result["state"] == "RISING"


def test_shipped_definition_gives_na_when_a_ticker_failed():
    defn = shipped_indicator("pair_change")
    frames = _ratio_frames([1] * 300)
    assert calc.run(defn, {"subject": frames["subject"], "benchmark": None})["reason"] == "fetch_failed"
    assert calc.run(defn, {"subject": frames["subject"]})["reason"] == "missing_role"
