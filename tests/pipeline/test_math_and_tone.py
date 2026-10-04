import math

import pandas as pd
import pytest

from pipeline.calc._math import linreg_slope, num, percentile_rank, sma, stdev
from pipeline.calc.tone import tone_for


def test_sma_needs_a_full_window():
    out = sma(pd.Series([1.0, 2.0, 3.0, 4.0]), 3)
    assert math.isnan(out[0]) and math.isnan(out[1])
    assert out[2] == 2.0 and out[3] == 3.0


def test_stdev_is_the_sample_standard_deviation():
    out = stdev(pd.Series([2.0, 4.0, 4.0, 6.0]), 4)
    # mean 4, squared deviations 4+0+0+4 = 8, divided by n-1 = 3
    assert out[3] == pytest.approx(math.sqrt(8 / 3))


def test_percentile_rank_bounds():
    sample = [1.0, 2.0, 3.0, 4.0]
    assert percentile_rank(4.0, sample) == 100.0      # highest reading
    assert percentile_rank(1.0, sample) == 25.0       # lowest = 1 / n
    assert percentile_rank(2.0, sample) == 50.0


def test_linreg_slope_of_a_straight_line():
    assert linreg_slope([1.0, 3.0, 5.0, 7.0]) == pytest.approx(2.0)
    assert linreg_slope([5.0, 5.0, 5.0]) == pytest.approx(0.0)


def test_num_turns_nan_into_none():
    assert num(float("nan"), 2) is None
    assert num(None, 2) is None
    assert num(1.23456, 2) == 1.23


STATE_MAP = {"type": "state_map", "map": {"BULLISH": "positive", "BEARISH": "negative"}}
SIGN = {"type": "sign", "key": "x"}
BANDS = {"type": "bands", "key": "p", "bands": [[33, "positive"], [67, "warning"], [100, "negative"]]}


def test_tone_state_map():
    assert tone_for(STATE_MAP, "BULLISH", {}) == "positive"
    assert tone_for(STATE_MAP, "NEUTRAL", {}) is None       # not in the map: no colour


def test_tone_sign():
    assert tone_for(SIGN, None, {"x": 0.01}) == "positive"
    assert tone_for(SIGN, None, {"x": -0.01}) == "negative"
    assert tone_for(SIGN, None, {"x": 0}) is None
    assert tone_for(SIGN, None, {}) is None


@pytest.mark.parametrize("value,expected", [
    (0, "positive"), (33, "positive"), (33.1, "warning"),
    (67, "warning"), (67.1, "negative"), (100, "negative"), (100.1, None),
])
def test_tone_bands_upper_bounds_are_inclusive(value, expected):
    assert tone_for(BANDS, None, {"p": value}) == expected


def test_no_rule_means_no_colour():
    assert tone_for(None, "BULLISH", {"x": 1}) is None
