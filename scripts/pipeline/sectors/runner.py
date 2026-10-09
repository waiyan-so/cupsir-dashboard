"""Run every sector indicator for every sector, then the cross-sector ops."""
import logging

from .. import calc
from .universe import SCOPE, sector_subjects

log = logging.getLogger("pipeline.sectors")


def _rank(rows, indicator_id, op):
    """Rank sectors by one value. N/A sectors take no part; their slot stays empty.
    Equal values share the better rank."""
    scored = []
    for row in rows:
        result = row["results"][indicator_id]
        if result["status"] != "ok":
            continue
        value = result["values"].get(op["value_key"])
        result["values"][op["target_key"]] = None
        if value is not None:
            scored.append((value, result))
    scored.sort(key=lambda pair: pair[0], reverse=(op["dir"] == "desc"))
    rank, previous = 0, None
    for position, (value, result) in enumerate(scored, start=1):
        if value != previous:
            rank, previous = position, value
        result["values"][op["target_key"]] = rank


CROSS_SECTION_OPS = {"rank": _rank}


def run(universe, indicators, store, scope=SCOPE):
    """rows for one sector scope's output file. `indicators` is [(id, definition)] for that
    scope; `store` is the PriceStore handed in by the orchestrator."""
    rows = []
    for subject in sector_subjects(universe, scope):
        frames = {role: store.get(ticker) for role, ticker in subject["roles"].items()}
        results = {}
        for iid, defn in indicators:
            try:
                results[iid] = calc.run(defn, frames)
            except Exception:  # noqa: BLE001 - one sector must not take down the rest
                log.exception("sector '%s' indicator '%s' failed", subject["id"], iid)
                results[iid] = calc.na("calc_error")
        rows.append({"id": subject["id"], "name_zh": subject["name_zh"],
                     "tickers": dict(subject["roles"]), "results": results})

    for iid, defn in indicators:
        for op in defn.get("cross_section", []):
            CROSS_SECTION_OPS[op["op"]](rows, iid, op)
    return rows
