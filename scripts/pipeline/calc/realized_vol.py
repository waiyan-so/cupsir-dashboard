"""Realized Volatility (spec 4.3): annualised standard deviation of daily log
returns over a short window, and where today's reading ranks against the
subject's own readings over the percentile window.

This measures moves that already happened. It is not an implied-volatility
index and is never labelled as one."""
import math

import numpy as np

from . import calculator
from ._math import date_str, num, percentile_rank, stdev

PCT_DIGITS = 2
PERCENTILE_DIGITS = 1


@calculator("realized_vol", params=("window", "percentile_window", "annualize", "history_days"))
def compute(frames, params):
    close = frames["subject"]["close"]
    daily_return = np.log(close / close.shift(1))
    rv = stdev(daily_return, params["window"]) * math.sqrt(params["annualize"]) * 100

    pwin = params["percentile_window"]
    sample = rv.tail(pwin)
    if sample.isna().any() or len(sample) < pwin:
        raise ValueError(f"need {pwin} volatility readings, have {int(sample.notna().sum())}")
    latest = rv.iloc[-1]
    return {
        "state": None,
        "values": {"annualized_pct": num(latest, PCT_DIGITS),
                   f"percentile_{pwin}d": num(percentile_rank(latest, sample.to_numpy()), PERCENTILE_DIGITS)},
        "history": [{"date": date_str(d), "annualized_pct": num(v, PCT_DIGITS)}
                    for d, v in rv.tail(params["history_days"]).items()],
        "events": [],
    }
