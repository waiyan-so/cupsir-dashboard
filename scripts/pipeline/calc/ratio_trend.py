"""Ratio Trend (spec F.3): the subject's close divided by the benchmark's close,
read the way a chart of "A / B" is read - where the ratio sits against its own
moving averages, and how far it has moved.

The state uses the same rule as the trend regime (spec 3.1), applied to the
ratio instead of a price, under names that do not imply good or bad: a rising
ratio is welcome for some pairs and a warning for others.

    RISING   ratio > fast > mid > slow and the mid average is rising
    FALLING  ratio < mid and ratio < slow and the mid average is falling
    MIXED    anything else

Ratios can be of any size (copper / gold is about 0.0016), so the output is
rounded to significant figures, not to a fixed number of decimals.
"""
from . import calculator
from ._math import date_str, num, sig
from .trend_regime import BEARISH, BULLISH, NEUTRAL, regime_table

RISING, FALLING, MIXED = "RISING", "FALLING", "MIXED"
STATE_OF_REGIME = {BULLISH: RISING, BEARISH: FALLING, NEUTRAL: MIXED}

RATIO_SIG = 6
PCT_DIGITS = 2

PARAMS = ("fast", "mid", "slow", "slope_window", "short_window", "long_window", "history_days")


def _change_pct(series, window):
    return (series.iloc[-1] / series.iloc[-1 - window] - 1) * 100


@calculator("ratio_trend", params=PARAMS)
def compute(frames, params):
    ratio = frames["subject"]["close"] / frames["benchmark"]["close"]
    table = regime_table(ratio, params)
    last = table.iloc[-1]
    fast, mid, slow = params["fast"], params["mid"], params["slow"]
    short, long_ = params["short_window"], params["long_window"]
    k_fast, k_mid, k_slow = f"sma{fast}", f"sma{mid}", f"sma{slow}"

    history = [
        {"date": date_str(d), "ratio": sig(r.close, RATIO_SIG), k_mid: sig(r.mid, RATIO_SIG), k_slow: sig(r.slow, RATIO_SIG)}
        for d, r in table.tail(params["history_days"]).iterrows()
    ] if params["history_days"] else []

    return {
        "state": STATE_OF_REGIME.get(last.state),
        "values": {
            "ratio": sig(last.close, RATIO_SIG),
            k_fast: sig(last.fast, RATIO_SIG),
            k_mid: sig(last.mid, RATIO_SIG),
            k_slow: sig(last.slow, RATIO_SIG),
            f"vs_sma{mid}_pct": num((last.close / last.mid - 1) * 100, PCT_DIGITS),
            f"vs_sma{slow}_pct": num((last.close / last.slow - 1) * 100, PCT_DIGITS),
            f"sma{mid}_rising": bool(last.slope > 0),
            f"change_{short}d_pct": num(_change_pct(ratio, short), PCT_DIGITS),
            f"change_{long_}d_pct": num(_change_pct(ratio, long_), PCT_DIGITS),
        },
        "history": history,
        "events": [],
    }
