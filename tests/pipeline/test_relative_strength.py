"""Relative Strength vs a benchmark (spec 4.4)."""
import math

import pytest

from pipeline import calc
from helpers import frame, shipped_indicator

DEFN = shipped_indicator("relative_strength")


def test_excess_returns_and_slope():
    n = 100
    bench = [100.0] * n
    bench[-1] = 104.0                    # benchmark +4 % over both windows
    sector = [50.0] * n
    sector[-1] = 55.0                    # sector +10 %
    result = calc.run(DEFN, {"subject": frame(sector), "benchmark": frame(bench)})
    v = result["values"]
    assert v["return_21d_excess_pct"] == pytest.approx(6.0)
    assert v["return_63d_excess_pct"] == pytest.approx(6.0)
    assert result["tone"] == "positive"
    assert result["history"] == [] and result["events"] == []


def test_windows_look_back_exactly_21_and_63_days():
    n = 100
    bench = [100.0] * n
    sector = [100.0] * n
    sector[-22] = 80.0                   # 21 sessions back
    sector[-64] = 50.0                   # 63 sessions back
    v = calc.run(DEFN, {"subject": frame(sector), "benchmark": frame(bench)})["values"]
    assert v["return_21d_excess_pct"] == pytest.approx(25.0)     # 100 / 80 - 1
    assert v["return_63d_excess_pct"] == pytest.approx(100.0)    # 100 / 50 - 1


def test_slope_of_a_steadily_outperforming_sector():
    n = 100
    bench = [100.0] * n
    sector = [100.0 * math.exp(0.001 * i) for i in range(n)]     # log ratio rises 0.001 a day
    v = calc.run(DEFN, {"subject": frame(sector), "benchmark": frame(bench)})["values"]
    assert v["rs_slope_21d"] == pytest.approx(0.001, abs=1e-6)


def test_underperformance_is_negative():
    n = 100
    bench = [100.0] * (n - 1) + [110.0]
    sector = [100.0] * n
    result = calc.run(DEFN, {"subject": frame(sector), "benchmark": frame(bench)})
    assert result["values"]["return_63d_excess_pct"] == pytest.approx(-10.0)
    assert result["tone"] == "negative"


def test_history_boundary_64_rows():
    need = DEFN["min_history_days"]
    a, b = [100.0] * need, [100.0] * need
    assert calc.run(DEFN, {"subject": frame(a), "benchmark": frame(b)})["status"] == "ok"
    assert calc.run(DEFN, {"subject": frame(a[:-1]), "benchmark": frame(b)})["reason"] == "insufficient_history"


def test_benchmark_download_failed():
    assert calc.run(DEFN, {"subject": frame([100.0] * 100), "benchmark": None})["reason"] == "fetch_failed"
