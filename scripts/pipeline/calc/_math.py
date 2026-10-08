"""Small numeric helpers shared by the calculators. Pure functions only."""
import math

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average. NaN until a full window is available."""
    return series.rolling(window, min_periods=window).mean()


def stdev(series: pd.Series, window: int) -> pd.Series:
    """Rolling sample standard deviation (n - 1 in the denominator). NaN until a full window."""
    return series.rolling(window, min_periods=window).std(ddof=1)


def percentile_rank(value: float, sample) -> float:
    """Share of `sample` that is less than or equal to `value`, as 0-100.

    `sample` normally includes `value` itself, so the highest reading of the
    sample scores 100 and the lowest scores 100 / len(sample).
    """
    arr = np.asarray(sample, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return float("nan")
    return float((arr <= value).sum()) / arr.size * 100.0


def linreg_slope(values) -> float:
    """Ordinary least squares slope of `values` against 0, 1, 2, ..."""
    y = np.asarray(values, dtype=float)
    n = y.size
    if n < 2 or np.isnan(y).any():
        return float("nan")
    x = np.arange(n, dtype=float)
    x_mean, y_mean = x.mean(), y.mean()
    denom = ((x - x_mean) ** 2).sum()
    return float(((x - x_mean) * (y - y_mean)).sum() / denom)


def num(value, digits: int):
    """Round to `digits` for output; None for NaN / infinity / missing."""
    if value is None:
        return None
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return None
    return round(value, digits)


def sig(value, digits: int):
    """Round to `digits` significant figures for output; None for NaN / infinity / missing.
    For values of any size: a ratio near 0.0016 keeps as much detail as one near 1.6."""
    if value is None:
        return None
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return None
    if value == 0:
        return 0.0
    return round(value, digits - 1 - int(math.floor(math.log10(abs(value)))))


def date_str(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")
