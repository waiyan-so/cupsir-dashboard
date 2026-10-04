"""Equal-weight vs cap-weight ratio (spec 3.3, 4.2)."""
import pytest

from pipeline import calc
from helpers import frame, shipped_indicator

DEFN = shipped_indicator("equal_weight_ratio")


def _run(equal_weight, cap_weight):
    return calc.run(DEFN, {"subject": frame(cap_weight), "equal_weight": frame(equal_weight)})


def test_ratio_normalized_and_roc():
    n = 120
    cap = [200.0] * n
    # ratio is 0.50 until 21 days before the end, then 0.55 on the last day
    eq = [100.0] * (n - 1) + [110.0]
    result = _run(eq, cap)
    v = result["values"]
    assert v["ratio"] == pytest.approx(0.55)
    assert v["roc_21d_pct"] == pytest.approx(10.0)          # 0.55 / 0.50 - 1
    assert v["normalized"] == pytest.approx(110.0)          # first day of the 90-day history = 100
    assert result["tone"] == "positive"                     # D1: rising ratio
    assert result["state"] is None


def test_falling_ratio_is_negative_and_flat_ratio_has_no_colour():
    n = 120
    cap = [200.0] * n
    assert _run([100.0] * (n - 1) + [95.0], cap)["tone"] == "negative"
    assert _run([100.0] * n, cap)["tone"] is None


def test_roc_looks_back_exactly_21_trading_days():
    n = 120
    cap = [100.0] * n
    eq = [50.0] * n
    eq[-22] = 40.0                   # the day 21 sessions before the last one
    assert _run(eq, cap)["values"]["roc_21d_pct"] == pytest.approx(25.0)   # 0.50 / 0.40 - 1
    eq[-22], eq[-23] = 50.0, 40.0    # one day further back: not used
    assert _run(eq, cap)["values"]["roc_21d_pct"] == pytest.approx(0.0)


def test_normalized_base_is_the_first_day_of_the_output_history():
    n = 200
    cap = [100.0] * n
    eq = [50.0] * n
    eq[-90] = 25.0                   # first day of the 90-day history
    result = _run(eq, cap)
    assert result["history"][0]["ratio"] == pytest.approx(0.25)
    assert result["values"]["normalized"] == pytest.approx(200.0)
    assert len(result["history"]) == 90 and set(result["history"][0]) == {"date", "ratio"}


def test_missing_equal_weight_etf():
    cap = frame([100.0] * 120)
    assert calc.run(DEFN, {"subject": cap})["reason"] == "missing_role"
    assert calc.run(DEFN, {"subject": cap, "equal_weight": None})["reason"] == "fetch_failed"


def test_history_boundary():
    need = DEFN["min_history_days"]
    assert _run([50.0] * need, [100.0] * need)["status"] == "ok"
    assert _run([50.0] * (need - 1), [100.0] * need)["reason"] == "insufficient_history"
