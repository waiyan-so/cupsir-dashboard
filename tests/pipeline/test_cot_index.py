"""COT Index / Sentiment Index (implementation guide 5.4)."""
import pandas as pd
import pytest

from pipeline import calc
from pipeline.calc.cot_index import classify, window_index
from helpers import shipped_indicator

DEFN_1Y = shipped_indicator("cot_index_1y")
THRESHOLDS = {k: DEFN_1Y["params"][k] for k in ("extreme_high", "extreme_low", "lean_high", "lean_low")}


def positions(commercial, nonreportable=None, start="2024-01-02"):
    idx = pd.date_range(start=start, periods=len(commercial), freq="W-TUE")
    nonreportable = commercial if nonreportable is None else nonreportable
    return pd.DataFrame({"commercial_net": [float(v) for v in commercial],
                         "nonreportable_net": [float(v) for v in nonreportable]}, index=idx)


def defn(lookback, history_points=52):
    params = dict(DEFN_1Y["params"], lookback=lookback, history_points=history_points)
    return dict(DEFN_1Y, min_history_days=lookback, params=params)


# ---- the index itself

def test_index_is_0_at_the_window_low_100_at_the_high_and_linear_between():
    out = window_index(pd.Series([10.0, 30.0, 20.0, 10.0, 30.0, 25.0]), 3)
    assert pd.isna(out[0]) and pd.isna(out[1])          # window not full yet
    assert out[2] == pytest.approx(50.0)                # 20 between 10 and 30
    assert out[3] == pytest.approx(0.0)                 # the lowest of 30, 20, 10
    assert out[4] == pytest.approx(100.0)               # the highest of 20, 10, 30
    assert out[5] == pytest.approx(75.0)                # 25 between 10 and 30


def test_window_counts_rows_and_must_be_full():
    result = calc.run(defn(4), {"positions": positions([5, 1, 9, 3])})      # exactly 4 rows
    assert result["status"] == "ok" and result["values"]["cot_index"] == 25.0     # (3 - 1) / (9 - 1)
    short = calc.run(defn(4), {"positions": positions([1, 9, 3])})           # 3 rows
    assert short["status"] == "na" and short["reason"] == "insufficient_history"


def test_window_uses_only_the_last_lookback_rows():
    # the 100 is five rows back, outside a 4-row window: the range is 1..9, not 1..100
    result = calc.run(defn(4), {"positions": positions([100, 5, 1, 9, 3])})
    assert result["values"]["cot_index"] == 25.0


def test_skipped_weeks_are_not_filled_in():
    frame = positions([5, 1, 9, 3])
    frame = frame.drop(frame.index[1])                    # a week the CFTC did not publish
    assert calc.run(defn(4), {"positions": frame})["reason"] == "insufficient_history"
    assert calc.run(defn(3), {"positions": frame})["values"]["cot_index"] == 0.0   # 3 is the low of 5, 9, 3


def test_flat_window_gives_no_value_instead_of_dividing_by_zero():
    result = calc.run(defn(3), {"positions": positions([7, 7, 7], [1, 2, 3])})
    assert result["status"] == "ok"
    assert result["values"]["cot_index"] is None and result["state"] is None and result["tone"] is None
    assert result["values"]["sentiment_index"] == 100.0


def test_values_history_and_data_date():
    frame = positions([0, 10, 20, 30, 40, 50], [50, 40, 30, 20, 10, 0])
    result = calc.run(defn(3, history_points=4), {"positions": frame})
    assert result["values"] == {"cot_index": 100.0, "sentiment_index": 0.0,
                                "commercial_net": 50, "nonreportable_net": 0}
    assert result["data_date"] == frame.index[-1].strftime("%Y-%m-%d")
    assert len(result["history"]) == 4
    assert result["history"][-1] == {"date": result["data_date"], "cot_index": 100.0, "sentiment_index": 0.0}
    assert set(result["history"][0]) == {"date", "cot_index", "sentiment_index"}


def test_history_points_before_the_window_is_full_are_empty_not_approximated():
    result = calc.run(defn(4, history_points=6), {"positions": positions([1, 2, 3, 4, 5, 6])})
    assert [p["cot_index"] for p in result["history"]] == [None, None, None, 100.0, 100.0, 100.0]


# ---- states (same thresholds as the existing cot_signal(), neutral wording)

@pytest.mark.parametrize("cot,sentiment,state", [
    (80, 20, "EXTREME_LONG"), (79.9, 20, "LONG_LEAN"), (80, 20.1, "LONG_LEAN"),
    (20, 80, "EXTREME_SHORT"), (20.1, 80, "SHORT_LEAN"), (20, 79.9, "SHORT_LEAN"),
    (70, 50, "LONG_LEAN"), (69.9, 50, "NEUTRAL"),
    (30, 50, "SHORT_LEAN"), (30.1, 50, "NEUTRAL"),
    (50, 50, "NEUTRAL"), (90, None, "LONG_LEAN"), (None, 50, None),
])
def test_state_boundaries(cot, sentiment, state):
    assert classify(cot, sentiment, THRESHOLDS) == state


def test_tones_follow_the_registry():
    rule = DEFN_1Y["tone_rule"]["map"]
    assert rule == {"EXTREME_LONG": "positive", "EXTREME_SHORT": "negative",
                    "LONG_LEAN": "positive", "SHORT_LEAN": "warning"}      # NEUTRAL: no colour
    up = calc.run(defn(3), {"positions": positions([1, 2, 3], [3, 2, 1])})
    assert up["state"] == "EXTREME_LONG" and up["tone"] == "positive"
    flat = calc.run(defn(3), {"positions": positions([1, 3, 2], [1, 3, 2])})
    assert flat["state"] == "NEUTRAL" and flat["tone"] is None


def test_three_shipped_lookbacks_share_one_calculator():
    lookbacks = {}
    for iid in ("cot_index_6m", "cot_index_1y", "cot_index_3y"):
        d = shipped_indicator(iid)
        assert d["calculator"] == "cot_index" and d["source"] == "cftc" and d["inputs"] == ["positions"]
        assert d["min_history_days"] == d["params"]["lookback"]          # a full window is required
        assert "cupsir" not in " ".join(d["expert_view"]).lower()
        lookbacks[iid] = d["params"]["lookback"]
    assert lookbacks == {"cot_index_6m": 26, "cot_index_1y": 52, "cot_index_3y": 156}


def test_no_download_gives_fetch_failed():
    assert calc.run(DEFN_1Y, {"positions": None})["reason"] == "fetch_failed"
