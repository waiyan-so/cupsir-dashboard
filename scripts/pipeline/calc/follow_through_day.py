"""
Follow-Through Day (FTD): a strong up day on higher volume, four or more
days into a rally attempt that follows a correction.

Formula: implementation guide section 4.4, which replaces spec 3.4 steps 1-4
with the approved revisions R1, R2, R3, R7 and the defaults F1-F4.
R5 (day-count tag) was approved by the owner on 2026-10-11: every FTD carries a
`timing` tag, IDEAL up to `ideal_max_day`, SLIGHTLY_LATE up to `late_after_day`,
LATE after that. It is a tag only and never removes an FTD. R6 (market-level
date) is not approved and not built: SPY and QQQ stay separate.

P1 as decided by the owner on 2026-10-11: the most recent `track_count` FTDs are
each followed on their own, whatever the state machine does next (track()).
The state machine itself is unchanged.

Chart window (2026-10-11): history and events start `chart_lead_days` before the
Day 1 of the oldest tracked FTD, or cover the last `chart_fallback_days` when
no FTD is tracked. It replaces the fixed `events_days` window.

F3 as revised by the owner on 2026-10-04: a new Day 1 is also looked for
while the state is CONFIRMED. When one is found the state moves to WATCHING
and the earlier FTD stays as last_confirmed_date. (The first version did not
look for Day 1 while CONFIRMED, which hid SPY's 2023-01-06 follow-through
day behind its still-standing 2022-10-21 one.)

On trading day t:
  peak      = the day with the highest close in the last `peak_window` days,
              t included (the most recent one if several tie)            [R3]
  low_i     = the day with the lowest intraday low after peak, up to and
              including t (the most recent one if several tie)           [R3]
  rally_low = low[low_i]
  premise   = between peak (exclusive) and low_i (inclusive) the close was
              below its `sma_fast` average on `below_sma_days` consecutive
              days, and the trend state on low_i is not BULLISH        [R7, F1]
  Day 1     = t, when t is the first higher close after low_i and the
              premise holds

replay() walks the days in order and is the single source of truth; compute()
only wraps its answer. Tests assert on replay()'s event list.
"""
import numpy as np

from . import calculator
from ._math import date_str, sma
from .trend_regime import BULLISH, PARAMS as TREND_PARAMS, regime_table

NONE_PENDING = "NONE_PENDING"
WATCHING = "WATCHING_RALLY_ATTEMPT"
CONFIRMED = "CONFIRMED"
FAILED = "FAILED"

IDEAL = "IDEAL"
SLIGHTLY_LATE = "SLIGHTLY_LATE"
LATE = "LATE"

ACTIVE = "ACTIVE"
NEW_HIGH = "NEW_HIGH"

DAY1 = "day1"
FTD = "ftd"
FAILED_EVENT = "failed"
RESET = "reset"

# Guards "exactly at the threshold" against binary floating point. Not tunable.
COMPARE_DIGITS = 12


def _last_argmax(values):
    return len(values) - 1 - int(np.argmax(values[::-1]))


def _last_argmin(values):
    return len(values) - 1 - int(np.argmin(values[::-1]))


def _has_run(flags, length):
    """True when `flags` holds at least `length` consecutive True values."""
    run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        if run >= length:
            return True
    return False


def timing(day_count, params):
    """R5: how late in its rally attempt an FTD came. A tag only."""
    if day_count <= params["ideal_max_day"]:
        return IDEAL
    if day_count <= params["late_after_day"]:
        return SLIGHTLY_LATE
    return LATE


def replay(df, params):
    """Replay the state machine over every day of `df`.

    Returns {"events": [...], "states": [...], "state", "attempt", "last_ftd"}.
    Each event: {"index", "date", "type", "day_count"}; an ftd event also has
    "low", "gain_pct", "above_avg_volume" and "timing". `states` holds the state at the
    end of each replayed day as (date, state).
    """
    close = df["close"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    volume = df["volume"].to_numpy(dtype=float)
    dates = df.index
    n = len(df)

    regime = regime_table(df["close"], params)["state"].to_numpy()
    fast = sma(df["close"], params["sma_fast"]).to_numpy()
    below = close < fast                      # False while the average is not available
    vol_avg = sma(df["volume"], params["vol_avg_window"]).to_numpy()
    peak_window = params["peak_window"]

    state = NONE_PENDING
    attempt = None                            # {"rally_low", "day_count", "low_index"}
    ftd = None                                # the FTD that put us in CONFIRMED / FAILED
    last_ftd = None
    events, states = [], []

    def emit(t, kind, day_count, **extra):
        events.append({"index": t, "date": date_str(dates[t]), "type": kind, "day_count": day_count, **extra})

    ready = [i for i in range(n) if regime[i] is not None]
    start = max(ready[0], 1) if ready else n

    for t in range(start, n):
        lo = max(0, t - peak_window + 1)
        peak = lo + _last_argmax(close[lo:t + 1])
        new_high = peak == t

        # 1. A confirmed FTD fails when the close undercuts the FTD day's low.
        if state == CONFIRMED and close[t] < ftd["low"]:
            state = FAILED
            emit(t, FAILED_EVENT, None)

        # 2. A new closing high for the window ends whatever was in progress (F2, F3, F4).
        if new_high:
            attempt = None
            state = NONE_PENDING

        # 3. A rally attempt in progress.
        if attempt is not None:
            if low[t] < attempt["rally_low"]:                                   # R1
                emit(t, RESET, attempt["day_count"])
                attempt = None
                if state == WATCHING:
                    state = NONE_PENDING
            else:
                attempt["day_count"] += 1
                gain = round(close[t] / close[t - 1] - 1, COMPARE_DIGITS)
                if (attempt["day_count"] >= params["min_day"]
                        and gain >= params["min_gain"]
                        and volume[t] > volume[t - 1]):
                    above = bool(not np.isnan(vol_avg[t]) and volume[t] > vol_avg[t])  # R2: a tag only
                    tag = timing(attempt["day_count"], params)                     # R5: a tag only
                    ftd = {"index": t, "date": date_str(dates[t]), "low": float(low[t]), "day1_index": attempt["day1_index"],
                           "day_count": attempt["day_count"], "above_avg_volume": above, "timing": tag}
                    last_ftd = ftd
                    emit(t, FTD, attempt["day_count"], low=float(low[t]), day1_index=attempt["day1_index"],
                         gain_pct=round(gain * 100, 2), above_avg_volume=above, timing=tag)
                    state = CONFIRMED
                    attempt = None

        # 4. Look for Day 1 of a new attempt - also while CONFIRMED (F3 as revised), but not
        #    on the day an FTD was just confirmed.
        if attempt is None and not new_high and not (ftd is not None and ftd["index"] == t):
            low_i = peak + 1 + _last_argmin(low[peak + 1:t + 1])
            if (low_i < t
                    and close[t] > close[t - 1]
                    and not any(close[j] > close[j - 1] for j in range(low_i + 1, t))
                    and regime[low_i] is not None and regime[low_i] != BULLISH
                    and _has_run(below[peak + 1:low_i + 1], params["below_sma_days"])):
                attempt = {"rally_low": float(low[low_i]), "day_count": 1, "low_index": low_i, "day1_index": t}
                state = WATCHING
                emit(t, DAY1, 1)

        states.append((date_str(dates[t]), state))

    return {"events": events, "states": states, "state": state, "attempt": attempt, "last_ftd": last_ftd}


def track(close, ftd_index, ftd_low, peak_window):
    """P1: follow one FTD after its day, on its own.

    FAILED   the first close below the FTD day's low                      (as step 1)
    NEW_HIGH the first close that is the highest of the last `peak_window`
             days, if it comes before any failure; tracking stops there
    ACTIVE   neither has happened yet
    A day that is both is FAILED, the order the state machine checks them in.
    Returns (status, index of the deciding day or None).
    """
    for k in range(ftd_index + 1, len(close)):
        if close[k] < ftd_low:
            return FAILED, k
        lo = max(0, k - peak_window + 1)
        if lo + _last_argmax(close[lo:k + 1]) == k:
            return NEW_HIGH, k
    return ACTIVE, None


@calculator("follow_through_day", params=TREND_PARAMS + (
    "peak_window", "min_day", "min_gain", "sma_fast", "below_sma_days", "vol_avg_window",
    "ideal_max_day", "late_after_day", "track_count", "track_tones", "chart_lead_days", "chart_fallback_days"))
def compute(frames, params):
    df = frames["subject"]
    out = replay(df, params)
    n = len(df)
    last_ftd = out["last_ftd"]
    close = df["close"].to_numpy(dtype=float)
    volume = df["volume"].to_numpy(dtype=float)
    vol_avg = sma(df["volume"], params["vol_avg_window"]).to_numpy()
    ftds = [e for e in out["events"] if e["type"] == FTD]
    tracked = {e["index"] for e in ftds[-params["track_count"]:]} if params["track_count"] > 0 else set()
    for e in ftds:
        status, k = track(close, e["index"], e["low"], params["peak_window"])
        e["status"], e["status_date"] = status, (date_str(df.index[k]) if k is not None else None)
        e["tracked"] = e["index"] in tracked
        e["tone"] = params["track_tones"].get(status)
    oldest_day1 = min((e["day1_index"] for e in ftds if e["tracked"]), default=None)
    first_shown = (max(0, oldest_day1 - params["chart_lead_days"]) if oldest_day1 is not None
                   else max(0, n - params["chart_fallback_days"]))
    for e in out["events"]:
        t = e["index"]
        e["change_pct"] = round((close[t] / close[t - 1] - 1) * 100, 2) if t > 0 else None
        e["volume_up"] = bool(t > 0 and volume[t] > volume[t - 1])
        e["above_avg_volume"] = bool(not np.isnan(vol_avg[t]) and volume[t] > vol_avg[t])
    avg_key = f"volume_sma{params['vol_avg_window']}"
    return {
        "state": out["state"],
        "values": {
            "last_confirmed_date": last_ftd["date"] if last_ftd else None,
            "days_since": (n - 1 - last_ftd["index"]) if last_ftd else None,
            "day_count": out["attempt"]["day_count"] if out["state"] == WATCHING and out["attempt"] else None,
            "above_avg_volume": last_ftd["above_avg_volume"] if last_ftd else None,
            "timing": last_ftd["timing"] if last_ftd else None,
        },
        "history": [{"date": date_str(df.index[i]), "close": round(float(close[i]), 2),
                     "volume": _number(volume[i]), avg_key: _number(vol_avg[i])} for i in range(first_shown, n)],
        "events": [_shown(e) for e in out["events"] if e["index"] >= first_shown],
    }


def _shown(event):
    shown = {"date": event["date"], "type": event["type"], "day_count": event["day_count"],
             "change_pct": event["change_pct"], "volume_up": event["volume_up"],
             "above_avg_volume": event["above_avg_volume"]}
    if event["type"] == FTD:
        for key in ("timing", "status", "status_date", "tracked", "tone"):
            shown[key] = event[key]
        shown["low"] = round(event["low"], 2)            # display only; track() uses the exact low
    return shown


def _number(value):
    return None if np.isnan(value) else round(float(value))
