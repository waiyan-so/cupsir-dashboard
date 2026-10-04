"""calc.run(): input checks and the Result envelope (spec A.4, A.5 b)."""
import pandas as pd

from pipeline import calc
from helpers import frame, shipped_indicator

ENVELOPE = {"status", "reason", "data_date", "state", "tone", "values", "history", "events"}


@calc.calculator("_test_last_close")
def _last_close(frames, params):
    return {"state": "UP", "values": {"close": frames["subject"]["close"].iloc[-1]},
            "history": [], "events": []}


@calc.calculator("_test_raises")
def _raises(frames, params):
    raise ZeroDivisionError("boom")


@calc.calculator("_test_incomplete")
def _incomplete(frames, params):
    return {"state": None, "values": {}}


def _defn(calculator="_test_last_close", inputs=("subject",), min_days=3, tone_rule=None):
    return {"calculator": calculator, "inputs": list(inputs), "min_history_days": min_days,
            "params": {}, "tone_rule": tone_rule}


def _assert_na(result, reason):
    assert set(result) == ENVELOPE
    assert result == {"status": "na", "reason": reason, "data_date": None, "state": None,
                      "tone": None, "values": {}, "history": [], "events": []}


def test_ok_result_has_the_full_envelope():
    rule = {"type": "state_map", "map": {"UP": "positive"}}
    result = calc.run(_defn(tone_rule=rule), {"subject": frame([1, 2, 3])})
    assert set(result) == ENVELOPE
    assert result["status"] == "ok" and result["reason"] is None
    assert result["data_date"] == "2024-01-04"
    assert result["state"] == "UP" and result["tone"] == "positive"
    assert result["values"] == {"close": 3.0}
    assert type(result["values"]["close"]) is float        # plain Python, not numpy


def test_missing_role():
    _assert_na(calc.run(_defn(inputs=("subject", "benchmark")), {"subject": frame([1, 2, 3])}),
               "missing_role")


def test_fetch_failed():
    _assert_na(calc.run(_defn(), {"subject": None}), "fetch_failed")


def test_history_just_enough_and_just_short():
    assert calc.run(_defn(min_days=3), {"subject": frame([1, 2, 3])})["status"] == "ok"
    _assert_na(calc.run(_defn(min_days=4), {"subject": frame([1, 2, 3])}), "insufficient_history")


def test_calculator_exception_becomes_calc_error():
    _assert_na(calc.run(_defn("_test_raises"), {"subject": frame([1, 2, 3])}), "calc_error")


def test_incomplete_answer_becomes_calc_error():
    _assert_na(calc.run(_defn("_test_incomplete"), {"subject": frame([1, 2, 3])}), "calc_error")


def test_roles_are_aligned_on_their_common_dates():
    a = frame([1, 2, 3, 4, 5])                      # 2024-01-02 .. 2024-01-08
    b = frame([1, 2, 3, 4], start="2024-01-02")     # one day shorter
    result = calc.run(_defn(inputs=("subject", "benchmark"), min_days=4), {"subject": a, "benchmark": b})
    assert result["status"] == "ok"
    assert result["data_date"] == "2024-01-05"      # last date both have
    assert result["values"]["close"] == 4.0         # the subject was cut to the common dates


def test_common_dates_too_few_is_insufficient_history():
    a = frame([1, 2, 3, 4])
    b = frame([1, 2, 3, 4], start="2024-01-04")     # only two dates overlap
    _assert_na(calc.run(_defn(inputs=("subject", "benchmark"), min_days=4), {"subject": a, "benchmark": b}),
               "insufficient_history")


def test_every_shipped_indicator_has_a_registered_calculator():
    import json
    from helpers import ROOT
    from pipeline import registry
    names = calc.registered()
    shipped = json.loads((ROOT / "config" / "indicators.json").read_text(encoding="utf-8"))["indicators"]
    assert {d["calculator"] for d in shipped.values()} <= names
    registry.load(ROOT / "config" / "indicators.json", ROOT / "config" / "universe.json", names)
