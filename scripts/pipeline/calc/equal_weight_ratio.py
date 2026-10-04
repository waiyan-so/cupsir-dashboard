"""Equal-weight vs cap-weight ratio (spec 3.3 and 4.2): the equal-weight ETF's
close divided by the cap-weight ETF's close. A rising ratio means the move is
broad; a falling ratio means it is concentrated in the largest names.

`normalized` sets the first day of the output history to 100."""
from . import calculator
from ._math import date_str, num

RATIO_DIGITS = 6
PCT_DIGITS = 2


@calculator("equal_weight_ratio", params=("roc_window", "history_days"))
def compute(frames, params):
    ratio = frames["equal_weight"]["close"] / frames["subject"]["close"]
    roc_window = params["roc_window"]
    roc = ratio.iloc[-1] / ratio.iloc[-1 - roc_window] - 1

    recent = ratio.tail(params["history_days"])
    normalized = 100 * ratio.iloc[-1] / recent.iloc[0]
    return {
        "state": None,
        "values": {"ratio": num(ratio.iloc[-1], RATIO_DIGITS),
                   "normalized": num(normalized, PCT_DIGITS),
                   f"roc_{roc_window}d_pct": num(roc * 100, PCT_DIGITS)},
        "history": [{"date": date_str(d), "ratio": num(v, RATIO_DIGITS)} for d, v in recent.items()],
        "events": [],
    }
