"""Trend Regime (spec 3.1). Small windows make the arithmetic checkable by hand."""
from pipeline import calc
from pipeline.calc.trend_regime import regime_table
from helpers import frame, shipped_indicator

SMALL = {"fast": 2, "mid": 3, "slow": 5, "slope_window": 1, "history_days": 90}


def _state(closes):
    return regime_table(frame(closes)["close"], SMALL)["state"].iloc[-1]


def test_bullish_stack_with_rising_mid_average():
    # fast (6+7)/2 = 6.5, mid (5+6+7)/3 = 6, slow 5, mid slope +1
    assert _state([1, 2, 3, 4, 5, 6, 7]) == "BULLISH"


def test_bullish_stack_but_flat_mid_average_is_neutral():
    # close 10 > fast 9 > mid 6.67 > slow 6.2, but mid slope = (10 - 10) / 3 = 0, and the rule needs > 0
    assert _state([1, 10, 2, 8, 10]) == "NEUTRAL"


def test_bearish():
    # close 5 < mid 6, close 5 < slow 7, mid slope -1
    assert _state([10, 9, 8, 7, 6, 5]) == "BEARISH"


def test_close_equal_to_mid_average_is_not_bearish():
    # mid (9+6+6)/3 = 7 ... make close equal mid: closes 8, 4, 6 -> mid 6 = close
    assert _state([12, 11, 10, 8, 4, 6]) == "NEUTRAL"


def test_flat_market_is_neutral():
    assert _state([5, 5, 5, 5, 5, 5, 5]) == "NEUTRAL"


def test_state_is_none_until_every_average_exists():
    table = regime_table(frame([1, 2, 3, 4, 5, 6, 7])["close"], SMALL)
    assert list(table["state"][:4]) == [None, None, None, None]
    assert table["state"].iloc[4] is not None


def test_shipped_definition_boundary_of_history():
    defn = shipped_indicator("trend_regime")
    need = defn["min_history_days"]                       # 205 = slow 200 + slope window 5
    rising = [100 + i * 0.5 for i in range(need)]
    ok = calc.run(defn, {"subject": frame(rising)})
    assert ok["status"] == "ok" and ok["state"] == "BULLISH" and ok["tone"] == "positive"
    assert set(ok["values"]) == {"close", "sma21", "sma50", "sma200", "slope50_5d"}
    assert all(v is not None for v in ok["values"].values())
    short = calc.run(defn, {"subject": frame(rising[:-1])})
    assert short["status"] == "na" and short["reason"] == "insufficient_history"


def test_history_is_capped_and_uses_the_chart_series_keys():
    defn = shipped_indicator("trend_regime")
    result = calc.run(defn, {"subject": frame([100 + i for i in range(400)])})
    assert len(result["history"]) == defn["params"]["history_days"]
    assert set(result["history"][-1]) == {"date"} | set(defn["detail_chart"]["series"])
    assert result["history"][-1]["date"] == result["data_date"]


def test_falling_market_is_bearish_and_negative():
    defn = shipped_indicator("trend_regime")
    result = calc.run(defn, {"subject": frame([400 - i * 0.5 for i in range(300)])})
    assert result["state"] == "BEARISH" and result["tone"] == "negative"
