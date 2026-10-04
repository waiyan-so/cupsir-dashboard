"""Realized Volatility (spec 4.3)."""
import math

import pytest

from pipeline import calc
from pipeline.calc.realized_vol import compute
from helpers import frame, shipped_indicator

DEFN = shipped_indicator("realized_vol")


def test_hand_checked_value_with_small_windows():
    params = {"window": 2, "percentile_window": 3, "annualize": 252, "history_days": 90}
    # daily log returns: ln 1.1, ln 1.1, 0, ln 1.2
    out = compute({"subject": frame([100, 110, 121, 121, 145.2])}, params)
    # last window = (0, ln 1.2): sample stdev = ln 1.2 / sqrt(2)
    expected = math.log(1.2) / math.sqrt(2) * math.sqrt(252) * 100
    assert out["values"]["annualized_pct"] == pytest.approx(expected, abs=0.01)
    # the three readings are 0, ln 1.1 / sqrt(2), ln 1.2 / sqrt(2) (annualised): the latest is the highest
    assert out["values"]["percentile_3d"] == 100.0


def test_hand_checked_percentile_in_the_middle():
    params = {"window": 2, "percentile_window": 3, "annualize": 252, "history_days": 90}
    # daily log returns: ln 1.1, ln 1.3, 0, ln 1.2 -> readings: small, large, middle
    out = compute({"subject": frame([100, 110, 143, 143, 171.6])}, params)
    # windows: (ln 1.1, ln 1.3) spread 0.167; (ln 1.3, 0) spread 0.262; (0, ln 1.2) spread 0.182
    assert out["values"]["percentile_3d"] == pytest.approx(66.7, abs=0.05)   # 2 of 3 readings <= latest


def _alternating(n, swing_small=0.001, swing_big=0.03, big_last=21):
    """Closes whose last `big_last` daily moves are large and all earlier ones small."""
    closes = [100.0]
    for i in range(1, n):
        swing = swing_big if i >= n - big_last else swing_small
        closes.append(closes[-1] * (1 + swing if i % 2 else 1 - swing))
    return closes


def test_latest_reading_highest_of_the_year_scores_100_and_is_red():
    need = DEFN["min_history_days"]
    result = calc.run(DEFN, {"subject": frame(_alternating(need))})
    assert result["values"]["percentile_252d"] == 100.0
    assert result["tone"] == "negative"                      # D2: above 67


def test_latest_reading_lowest_of_the_year_scores_one_over_n_and_is_green():
    need = DEFN["min_history_days"]
    closes = _alternating(need, swing_small=0.03, swing_big=0.001)
    result = calc.run(DEFN, {"subject": frame(closes)})
    assert result["values"]["percentile_252d"] == pytest.approx(100 / 252, abs=0.05)
    assert result["tone"] == "positive"                      # D2: 33 or below


def test_history_boundary_273_rows():
    need = DEFN["min_history_days"]
    assert need == DEFN["params"]["percentile_window"] + DEFN["params"]["window"]
    closes = _alternating(need)
    assert calc.run(DEFN, {"subject": frame(closes)})["status"] == "ok"
    assert calc.run(DEFN, {"subject": frame(closes[:-1])})["reason"] == "insufficient_history"


def test_too_low_min_history_in_the_registry_gives_calc_error_not_a_wrong_number():
    defn = dict(DEFN, min_history_days=100)
    assert calc.run(defn, {"subject": frame(_alternating(150))})["reason"] == "calc_error"


def test_history_for_the_chart():
    result = calc.run(DEFN, {"subject": frame(_alternating(400))})
    assert len(result["history"]) == DEFN["params"]["history_days"]
    assert set(result["history"][0]) == {"date", "annualized_pct"}
