"""
Orchestration layer (spec section 6): the single entry point of the market
breadth / sector / COT pipeline and the only code that writes data/.

    python scripts/run_pipeline.py                 normal run
    python scripts/run_pipeline.py --dry-run       run everything, write nothing
    python scripts/run_pipeline.py --offline DIR   read CSV files in DIR instead of the network
    python scripts/run_pipeline.py --registry FILE use another indicator registry

Exit codes: 0 written (cells that failed show N/A), 1 nothing could be
computed (previous output kept), 2 config invalid (previous output kept).

Independent of build_dashboard.py and data/dashboard.json: nothing here feeds
the dashboard's total score.
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline import calc, registry, sectors
from pipeline.collect import cftc, fixtures, prices

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"

SCHEMA_VERSION = 2
MARKET_FILE = "market_breadth.json"
SECTOR_FILE = "sectors.json"
COT_FILE = "cot.json"

EXIT_OK, EXIT_NO_DATA, EXIT_BAD_CONFIG = 0, 1, 2

# Registry fields the front end needs. params, notes and calculator stay out.
META_COMMON = ("name", "name_zh", "detail_chart", "value_labels", "expert_view", "disclaimer")


def _say(message):
    print(f"[pipeline] {message}")


def _meta_indicators(indicators, scope):
    out = []
    for iid, d in indicators:
        entry = {"id": iid}
        entry.update({k: d.get(k) for k in META_COMMON})
        entry.update(d["scopes"][scope])
        out.append(entry)
    return sorted(out, key=lambda e: e["order"])


def _frames_for(subject, store):
    return {role: store.get(ticker) for role, ticker in subject["roles"].items()}


def _market_tickers(universe, indicators):
    by_id = {s["id"]: s for s in registry.subjects(universe, "market")}
    tickers = set()
    for _, d in indicators:
        for sid in d["scopes"]["market"]["subjects"]:
            for role in d["inputs"]:
                if role in by_id[sid]["roles"]:
                    tickers.add(by_id[sid]["roles"][role])
    return tickers


def build_market(universe, indicators_cfg, indicators, store):
    by_id = {s["id"]: s for s in registry.subjects(universe, "market")}
    results = {}
    for iid, d in indicators:
        results[iid] = {sid: calc.run(d, _frames_for(by_id[sid], store))
                        for sid in d["scopes"]["market"]["subjects"]}
    used = {sid for _, d in indicators for sid in d["scopes"]["market"]["subjects"]}
    meta = {
        "ui_labels": indicators_cfg["ui_labels"],
        "subjects": [{"id": s["id"], "name_zh": s["name_zh"], "ticker": s["roles"]["subject"]}
                     for s in registry.subjects(universe, "market") if s["id"] in used],
        "indicators": _meta_indicators(indicators, "market"),
    }
    cells = [(iid, sid, r) for iid, per_subject in results.items() for sid, r in per_subject.items()]
    return {"meta": meta, "results": results}, cells


def build_sectors(universe, indicators_cfg, indicators, store):
    rows = sectors.run(universe, indicators, store)
    table = indicators_cfg.get("sector_table", {})
    meta = {
        "ui_labels": indicators_cfg["ui_labels"],
        "default_sort": table.get("default_sort"),
        "tie_break": table.get("tie_break"),
        "indicators": _meta_indicators(indicators, "sector"),
    }
    cells = [(iid, row["id"], row["results"][iid]) for row in rows for iid, _ in indicators]
    return {"meta": meta, "rows": rows}, cells


def build_cot(universe, indicators_cfg, indicators, store):
    """One row per COT market. Markets are not compared with each other, so there is no
    layer of its own for them: the orchestrator calls the calculation layer directly."""
    rows = []
    for subject in registry.subjects(universe, "cot"):
        frame = store.get(subject["cftc_code"])
        results = {iid: calc.run(d, {"positions": frame}) for iid, d in indicators}
        rows.append({"id": subject["id"], "name_zh": subject["name_zh"], "group": subject["group"],
                     "cftc": {"code": subject["cftc_code"], "name": subject["cftc_name"],
                              "rows": 0 if frame is None else len(frame)},
                     "results": results})
    meta = {
        "ui_labels": indicators_cfg["ui_labels"],
        "default_sort": None,
        "tie_break": None,
        "groups": universe.get("cot", {}).get("groups", {}),
        "indicators": _meta_indicators(indicators, "cot"),
    }
    cells = [(iid, row["id"], row["results"][iid]) for row in rows for iid, _ in indicators]
    return {"meta": meta, "rows": rows}, cells


class OutputMismatch(Exception):
    """The registry points at something the results do not contain."""


def _referenced_keys(scope, iid, d, table):
    """(where in the registry, key) for every values key the registry refers to."""
    block = d["scopes"][scope]
    refs = [(f"scopes.{scope}.value_key", block["value_key"])]
    if "secondary_key" in block:
        refs.append((f"scopes.{scope}.secondary_key", block["secondary_key"]))
    rule = d.get("tone_rule") or {}
    if "key" in rule:
        refs.append(("tone_rule.key", rule["key"]))
    if scope == "sector":
        refs += [(f"cross_section[{i}].value_key", op["value_key"]) for i, op in enumerate(d.get("cross_section", []))]
        for name in ("default_sort", "tie_break"):
            sort = table.get(name)
            if sort and sort["indicator"] == iid:
                refs.append((f"sector_table.{name}.value_key", sort["value_key"]))
    return [(where, key) for where, key in refs if key != "state"]


def check_cells(scope, indicators, cells, expected, table):
    """Spec 6.1 step 7. Every enabled indicator has a complete Result for every subject it
    should cover, and every key the registry names (value_key, tone_rule.key, chart series...)
    really exists in what the calculator returned."""
    have = {(iid, sid) for iid, sid, _ in cells}
    missing = expected - have
    if missing:
        raise OutputMismatch(f"output is missing results for {sorted(missing)}")
    defs = dict(indicators)
    for iid, sid, result in cells:
        lacking = [k for k in calc.RESULT_KEYS if k not in result]
        if lacking:
            raise OutputMismatch(f"result {iid}/{sid} lacks {lacking}")
        if result["status"] != "ok":
            continue
        d = defs[iid]
        for where, key in _referenced_keys(scope, iid, d, table):
            if key not in result["values"]:
                raise OutputMismatch(f"indicators.{iid}.{where}: 「{key}」不在計算結果的 values 之內"
                                     f"（現有：{sorted(result['values'])}）")
        chart = d.get("detail_chart")
        if chart and result["history"]:
            for key in chart["series"]:
                if key not in result["history"][0]:
                    raise OutputMismatch(f"indicators.{iid}.detail_chart.series: 「{key}」不在 history 之內"
                                         f"（現有：{sorted(result['history'][0])}）")


def summarise(scope, cells):
    """Print one line per indicator: how many ok, how many N/A and why. Returns the ok count."""
    by_indicator = {}
    for iid, sid, result in cells:
        by_indicator.setdefault(iid, []).append((sid, result))
    ok_total = 0
    for iid, items in by_indicator.items():
        ok = sum(1 for _, r in items if r["status"] == "ok")
        ok_total += ok
        reasons = {}
        for sid, r in items:
            if r["status"] != "ok":
                reasons.setdefault(r["reason"], []).append(sid)
        line = f"{scope} / {iid}: {ok} ok, {len(items) - ok} na"
        if reasons:
            detail = "; ".join(f"{reason}: {', '.join(sids)}" for reason, sids in sorted(reasons.items()))
            print(f"::warning::{line} ({detail})")
        else:
            _say(line)
    return ok_total


def write_json(path, payload):
    """Write to a temporary file first, then rename, so a crash never leaves half a file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def _report_store(label, needed, store):
    _say(f"{label}: {len(needed)} needed, {store.ok_count()} ok")
    for key, message in sorted(store.errors.items()):
        print(f"::warning::{label} {key}: {store.status[key]} - {message}")


def main(argv=None, data_dir=DATA_DIR, config_dir=CONFIG_DIR, fetch=None, fetch_cftc=None):
    parser = argparse.ArgumentParser(description="Build market breadth and sector data.")
    parser.add_argument("--dry-run", action="store_true", help="run everything but write no file")
    parser.add_argument("--offline", metavar="DIR", help="read CSV files in DIR instead of the network")
    parser.add_argument("--registry", metavar="FILE", help="indicator registry to use instead of config/indicators.json")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    data_dir, config_dir = Path(data_dir), Path(config_dir)

    # 1. Read and validate the config.
    try:
        indicators_cfg, universe = registry.load(
            args.registry or config_dir / "indicators.json", config_dir / "universe.json", calc.registered())
        sectors.validate(universe)
    except (registry.RegistryError, ValueError) as e:
        print(f"::error::config invalid, nothing written: {e}")
        return EXIT_BAD_CONFIG

    market_inds = registry.enabled_indicators(indicators_cfg, "market")
    sector_inds = registry.enabled_indicators(indicators_cfg, "sector")
    cot_inds = registry.enabled_indicators(indicators_cfg, "cot")

    # 2-3. Work out what each source must deliver and fetch every item once.
    tickers = _market_tickers(universe, market_inds) | sectors.required_tickers(universe, sector_inds)
    codes = {s["cftc_code"] for s in registry.subjects(universe, "cot")} if cot_inds else set()
    if args.offline:
        store = fixtures.load_prices(args.offline, tickers)
        positions = fixtures.load_positions(args.offline, codes)
    else:
        store = (fetch or prices.fetch_prices)(tickers)
        positions = (fetch_cftc or cftc.fetch_positions)(codes)
    _report_store("tickers", tickers, store)
    _report_store("cftc codes", codes, positions)

    # 4-7. Compute both scopes, build the payloads, check them.
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    outputs = []
    for scope, filename, builder, inds, source in (
        ("market", MARKET_FILE, build_market, market_inds, store),
        ("sector", SECTOR_FILE, build_sectors, sector_inds, store),
        ("cot", COT_FILE, build_cot, cot_inds, positions),
    ):
        body, cells = builder(universe, indicators_cfg, inds, source)
        if scope == "market":
            expected = {(iid, sid) for iid, d in inds for sid in d["scopes"]["market"]["subjects"]}
        else:
            expected = {(iid, s["id"]) for iid, _ in inds for s in registry.subjects(universe, scope)}
        try:
            check_cells(scope, inds, cells, expected, indicators_cfg.get("sector_table", {}))
        except OutputMismatch as e:
            print(f"::error::config does not match the results, nothing written: {e}")
            return EXIT_BAD_CONFIG
        ok = summarise(scope, cells)
        payload = {"schema_version": SCHEMA_VERSION, "updated_at": updated_at, **body}
        outputs.append((filename, payload, ok, len(cells)))

    # 8. Write. A file whose every result failed is not written, so the last good one stays.
    #    A scope with no enabled indicator is not a failure: its (empty) file is written.
    written = 0
    for filename, payload, ok, total in outputs:
        if total and ok == 0:
            print(f"::warning::{filename}: no result could be computed, previous file kept")
            continue
        written += 1
        if args.dry_run:
            _say(f"dry run: {filename} not written")
        else:
            data_dir.mkdir(parents=True, exist_ok=True)
            write_json(data_dir / filename, payload)
            _say(f"wrote {filename}")
    if written == 0:
        print("::error::no data could be computed, nothing written")
        return EXIT_NO_DATA
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
