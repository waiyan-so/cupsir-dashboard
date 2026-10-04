"""
Calculation layer (spec A.5 b).

One file per calculator, registered with @calculator("id"). Every calculator
has the same signature:

    compute(frames, params) -> {"state", "values", "history", "events"}

`frames` maps a role name (subject / equal_weight / benchmark) to a frame
that shares one date index with the other roles. Calculators are pure: no
network, no file access, no clock. Every number they use comes from `params`.

run(indicator_def, frames) is the only entry point other layers call. It
checks the inputs, calls the calculator, and wraps the answer in the Result
envelope every indicator shares (spec A.4).
"""
import importlib
import logging
import math
import pkgutil

from .tone import tone_for

log = logging.getLogger("pipeline.calc")

_REGISTRY = {}
_REQUIRED_PARAMS = {}
_loaded = False

RESULT_KEYS = ("status", "reason", "data_date", "state", "tone", "values", "history", "events")
CALC_KEYS = ("state", "values", "history", "events")


def calculator(name, params=()):
    """Register a calculator function under `name`.
    `params` lists the keys the function reads from its params, so the registry
    can reject a config that leaves one out before anything runs."""
    def deco(fn):
        if name in _REGISTRY and _REGISTRY[name] is not fn:
            raise ValueError(f"calculator '{name}' is registered twice")
        _REGISTRY[name] = fn
        _REQUIRED_PARAMS[name] = tuple(params)
        return fn
    return deco


def _load_all():
    """Import every module in this package so its @calculator runs.
    Adding a calculator therefore means adding one file and nothing else."""
    global _loaded
    if _loaded:
        return
    for mod in pkgutil.iter_modules(__path__):
        if not mod.name.startswith("_"):
            importlib.import_module(f"{__name__}.{mod.name}")
    _loaded = True


def registered():
    """{calculator name: params it requires} for every registered calculator."""
    _load_all()
    return dict(_REQUIRED_PARAMS)


def na(reason):
    return {"status": "na", "reason": reason, "data_date": None, "state": None, "tone": None,
            "values": {}, "history": [], "events": []}


def _clean(obj):
    """Make the calculator's answer JSON-safe: plain Python types, NaN -> None."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if hasattr(obj, "item"):          # numpy scalar
        obj = obj.item()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def run(indicator_def, frames):
    """Compute one indicator for one subject and return a Result.

    frames: {role: frame or None}. A role missing from the dict means the
    subject has no ticker for that role; None means the download failed.
    """
    _load_all()
    roles = indicator_def["inputs"]
    for role in roles:
        if role not in frames:
            return na("missing_role")
    for role in roles:
        if frames[role] is None:
            return na("fetch_failed")

    need = indicator_def["min_history_days"]
    common = frames[roles[0]].index
    for role in roles[1:]:
        common = common.intersection(frames[role].index)
    if any(len(frames[role]) < need for role in roles) or len(common) < need:
        return na("insufficient_history")

    aligned = {role: frames[role].loc[common] for role in roles}
    try:
        out = _REGISTRY[indicator_def["calculator"]](aligned, indicator_def["params"])
        missing = [k for k in CALC_KEYS if k not in out]
        if missing:
            raise KeyError(f"calculator answer lacks {missing}")
        out = _clean({k: out[k] for k in CALC_KEYS})
    except Exception:  # noqa: BLE001 - one bad cell must not stop the run
        log.exception("calculator '%s' failed", indicator_def.get("calculator"))
        return na("calc_error")

    return {
        "status": "ok",
        "reason": None,
        "data_date": common[-1].strftime("%Y-%m-%d"),
        "state": out["state"],
        "tone": tone_for(indicator_def.get("tone_rule"), out["state"], out["values"]),
        "values": out["values"],
        "history": out["history"],
        "events": out["events"],
    }
