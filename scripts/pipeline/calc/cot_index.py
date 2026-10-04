"""COT Index and Sentiment Index (Larry Williams' method): where this week's
net position sits between its lowest and highest reading of the lookback
window, as 0-100.

  COT Index        from the commercial traders' net position
  Sentiment Index  from the non-reportable (small speculator) net position

The window must be full - no value is given on fewer than `lookback` rows -
and it counts rows, not calendar weeks (the CFTC occasionally skips a week).
When the window's highest and lowest readings are equal there is no value.

States describe the commercial traders' positioning in that one market. They
are not a view on the stock market and not a buy or sell instruction.
"""
import pandas as pd

from . import calculator
from ._math import date_str, num

EXTREME_LONG = "EXTREME_LONG"
EXTREME_SHORT = "EXTREME_SHORT"
LONG_LEAN = "LONG_LEAN"
SHORT_LEAN = "SHORT_LEAN"
NEUTRAL = "NEUTRAL"

INDEX_DIGITS = 1


def window_index(series: pd.Series, lookback: int) -> pd.Series:
    low = series.rolling(lookback, min_periods=lookback).min()
    high = series.rolling(lookback, min_periods=lookback).max()
    span = high - low
    return ((series - low) / span.where(span != 0) * 100)


def classify(cot, sentiment, params):
    if cot is None:
        return None
    if sentiment is not None:
        if cot >= params["extreme_high"] and sentiment <= params["extreme_low"]:
            return EXTREME_LONG
        if cot <= params["extreme_low"] and sentiment >= params["extreme_high"]:
            return EXTREME_SHORT
    if cot >= params["lean_high"]:
        return LONG_LEAN
    if cot <= params["lean_low"]:
        return SHORT_LEAN
    return NEUTRAL


@calculator("cot_index", params=("lookback", "history_points", "extreme_high", "extreme_low", "lean_high", "lean_low"))
def compute(frames, params):
    positions = frames["positions"]
    cot = window_index(positions["commercial_net"], params["lookback"])
    sentiment = window_index(positions["nonreportable_net"], params["lookback"])

    latest_cot = num(cot.iloc[-1], INDEX_DIGITS)
    latest_sentiment = num(sentiment.iloc[-1], INDEX_DIGITS)
    recent = positions.index[-params["history_points"]:]
    return {
        "state": classify(latest_cot, latest_sentiment, params),
        "values": {
            "cot_index": latest_cot,
            "sentiment_index": latest_sentiment,
            "commercial_net": int(positions["commercial_net"].iloc[-1]),
            "nonreportable_net": int(positions["nonreportable_net"].iloc[-1]),
        },
        "history": [{"date": date_str(d), "cot_index": num(cot[d], INDEX_DIGITS),
                     "sentiment_index": num(sentiment[d], INDEX_DIGITS)} for d in recent],
        "events": [],
    }
