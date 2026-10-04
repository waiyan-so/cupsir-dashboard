"""Relative Strength against a benchmark (spec 4.4): excess return over two
windows and the slope of the log price ratio. Ranking across sectors is not
done here - the sector layer adds it (cross_section in the registry)."""
import numpy as np

from . import calculator
from ._math import linreg_slope, num

PCT_DIGITS = 2
SLOPE_DIGITS = 6


def _ret(close, window):
    return close.iloc[-1] / close.iloc[-1 - window] - 1


@calculator("relative_strength")
def compute(frames, params):
    subject = frames["subject"]["close"]
    benchmark = frames["benchmark"]["close"]
    short, long_, slope_window = params["short_window"], params["long_window"], params["slope_window"]

    log_ratio = np.log(subject / benchmark)
    return {
        "state": None,
        "values": {
            f"return_{short}d_excess_pct": num((_ret(subject, short) - _ret(benchmark, short)) * 100, PCT_DIGITS),
            f"return_{long_}d_excess_pct": num((_ret(subject, long_) - _ret(benchmark, long_)) * 100, PCT_DIGITS),
            f"rs_slope_{slope_window}d": num(linreg_slope(log_ratio.tail(slope_window).to_numpy()), SLOPE_DIGITS),
        },
        "history": [],
        "events": [],
    }
