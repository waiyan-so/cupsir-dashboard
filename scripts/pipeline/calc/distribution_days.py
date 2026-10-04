"""Distribution Days (spec 3.2): days that close lower by at least a set
percentage on higher volume than the day before, counted over a window."""
from . import calculator
from ._math import date_str, num

NORMAL = "NORMAL"
WARNING = "WARNING"
HIGH_PRESSURE = "HIGH_PRESSURE"

PRICE_DIGITS = 2
PCT_DIGITS = 2
RATIO_DIGITS = 2
# Guards the "exactly at the threshold" case against binary floating point
# (99.8 / 100 - 1 is not exactly -0.002). Not a tunable threshold.
COMPARE_DIGITS = 12


@calculator("distribution_days", params=("decline_threshold", "window", "warning_count", "high_count", "history_days"))
def compute(frames, params):
    df = frames["subject"]
    close, volume = df["close"], df["volume"]
    pct = (close / close.shift(1) - 1).round(COMPARE_DIGITS)
    is_dd = (pct <= params["decline_threshold"]) & (volume > volume.shift(1))

    window = params["window"]
    in_window = is_dd.tail(window)
    count = int(in_window.sum())

    if count >= params["high_count"]:
        state = HIGH_PRESSURE
    elif count >= params["warning_count"]:
        state = WARNING
    else:
        state = NORMAL

    events = [
        {"date": date_str(d), "pct_change": num(pct[d] * 100, PCT_DIGITS),
         "volume_ratio": num(volume[d] / volume.shift(1)[d], RATIO_DIGITS)}
        for d in in_window.index[in_window]
    ]
    history = [{"date": date_str(d), "close": num(v, PRICE_DIGITS)}
               for d, v in close.tail(params["history_days"]).items()]
    return {
        "state": state,
        "values": {f"count_{window}d": count},
        "history": history,
        "events": events,
    }
