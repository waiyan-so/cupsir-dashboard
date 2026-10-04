"""Distribution Days (spec 3.2)."""
import pytest

from pipeline import calc
from helpers import frame, shipped_indicator

DEFN = shipped_indicator("distribution_days")
KEY = "count_25d"


def _run(closes, volumes):
    return calc.run(DEFN, {"subject": frame(closes, volumes)})


def _flat(n=40):
    return [100.0] * n, [1000.0] * n


def test_fall_of_exactly_the_threshold_on_higher_volume_counts():
    closes, volumes = _flat()
    closes[-1], volumes[-1] = 99.8, 1001          # exactly -0.2 %
    result = _run(closes, volumes)
    assert result["values"][KEY] == 1
    assert result["events"] == [{"date": result["data_date"], "pct_change": -0.2, "volume_ratio": 1.0}]


def test_fall_just_short_of_the_threshold_does_not_count():
    closes, volumes = _flat()
    closes[-1], volumes[-1] = 99.81, 2000         # -0.19 %
    assert _run(closes, volumes)["values"][KEY] == 0


def test_equal_volume_does_not_count():
    closes, volumes = _flat()
    closes[-1] = 99.0                             # -1 %, volume unchanged
    assert _run(closes, volumes)["values"][KEY] == 0


def test_lower_volume_does_not_count():
    closes, volumes = _flat()
    closes[-1], volumes[-1] = 99.0, 999
    assert _run(closes, volumes)["values"][KEY] == 0


def _with_drops(positions_from_end, n=60):
    """Flat series with a 1 % drop on higher volume at each given offset from the last day
    (0 = last day). Each drop is followed by a recovery so later days are not affected."""
    closes, volumes = [100.0] * n, [1000.0] * n
    for off in positions_from_end:
        i = n - 1 - off
        closes[i] = 99.0
        volumes[i] = 2000
    return closes, volumes


def test_window_is_the_last_25_trading_days():
    # offset 24 is the oldest day inside the window, offset 26 is outside it
    assert _run(*_with_drops([24]))["values"][KEY] == 1
    assert _run(*_with_drops([26]))["values"][KEY] == 0


@pytest.mark.parametrize("drops,state,tone", [
    (2, "NORMAL", "positive"),
    (3, "WARNING", "warning"),
    (4, "WARNING", "warning"),
    (5, "HIGH_PRESSURE", "negative"),
])
def test_state_thresholds(drops, state, tone):
    offsets = [i * 2 for i in range(drops)]       # every other day, so each drop is from 100
    result = _run(*_with_drops(offsets))
    assert result["values"][KEY] == drops
    assert result["state"] == state and result["tone"] == tone
    assert len(result["events"]) == drops


def test_ex_dividend_gap_is_only_a_distribution_day_on_unadjusted_prices():
    # A fund trading flat at 100 pays 1.00. Unadjusted, the ex-dividend day shows 99 (-1 %).
    # Adjusted prices scale the earlier days down instead, so no fall appears.
    n = 40
    volumes = [1000.0] * (n - 1) + [1500.0]
    unadjusted = [100.0] * (n - 1) + [99.0]
    adjusted = [99.0] * n
    assert _run(unadjusted, volumes)["values"][KEY] == 1
    assert _run(adjusted, volumes)["values"][KEY] == 0


def test_history_carries_closes_for_the_chart():
    result = _run(*_flat(120))
    assert len(result["history"]) == DEFN["params"]["history_days"]
    assert set(result["history"][0]) == {"date", "close"}


def test_history_boundary():
    need = DEFN["min_history_days"]
    assert _run(*_flat(need))["status"] == "ok"
    assert _run(*_flat(need - 1))["reason"] == "insufficient_history"
