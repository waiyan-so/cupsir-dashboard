"""Trend Regime (spec 3.1): where the close sits against three moving averages
and whether the middle one is rising. Shared by the market and sector scopes;
follow_through_day reuses regime_table() for its per-day trend state."""
import pandas as pd

from . import calculator
from ._math import date_str, num, sma

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NEUTRAL = "NEUTRAL"

PRICE_DIGITS = 2
SLOPE_DIGITS = 4


def regime_table(close: pd.Series, params) -> pd.DataFrame:
    """Per-day fast / mid / slow averages, mid slope and state.
    `state` is None on days where an average is not available yet."""
    fast = sma(close, params["fast"])
    mid = sma(close, params["mid"])
    slow = sma(close, params["slow"])
    slope = mid - mid.shift(params["slope_window"])

    bullish = (close > fast) & (fast > mid) & (mid > slow) & (slope > 0)
    bearish = (close < mid) & (close < slow) & (slope < 0)
    ready = fast.notna() & mid.notna() & slow.notna() & slope.notna()

    state = pd.Series(NEUTRAL, index=close.index, dtype=object)
    state[bearish] = BEARISH
    state[bullish] = BULLISH
    state[~ready] = None
    return pd.DataFrame({"close": close, "fast": fast, "mid": mid, "slow": slow,
                         "slope": slope, "state": state})


def _keys(params):
    return (f"sma{params['fast']}", f"sma{params['mid']}", f"sma{params['slow']}",
            f"slope{params['mid']}_{params['slope_window']}d")


@calculator("trend_regime")
def compute(frames, params):
    table = regime_table(frames["subject"]["close"], params)
    k_fast, k_mid, k_slow, k_slope = _keys(params)
    last = table.iloc[-1]

    history = [
        {"date": date_str(d), "close": num(r.close, PRICE_DIGITS), k_fast: num(r.fast, PRICE_DIGITS),
         k_mid: num(r.mid, PRICE_DIGITS), k_slow: num(r.slow, PRICE_DIGITS)}
        for d, r in table.tail(params["history_days"]).iterrows()
    ]
    return {
        "state": last.state,
        "values": {"close": num(last.close, PRICE_DIGITS), k_fast: num(last.fast, PRICE_DIGITS),
                   k_mid: num(last.mid, PRICE_DIGITS), k_slow: num(last.slow, PRICE_DIGITS),
                   k_slope: num(last.slope, SLOPE_DIGITS)},
        "history": history,
        "events": [],
    }
