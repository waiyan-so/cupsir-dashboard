"""Design invariants of spec A.6, checked against the source files themselves."""
import ast
import json
import re
from pathlib import Path

from helpers import ROOT

SCRIPTS = ROOT / "scripts"
PIPELINE = SCRIPTS / "pipeline"
ORCHESTRATOR = SCRIPTS / "run_pipeline.py"
FRONT_END = ROOT / "web" / "breadth.js"
EXISTING_SCRIPTS = {"config", "build_dashboard", "fetch_events", "fetch_news", "generate_summary"}


def sources(folder):
    return sorted(p for p in Path(folder).rglob("*.py"))


def imports(path):
    """Module names imported by a file, with relative imports resolved to dotted names."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = list(path.relative_to(SCRIPTS).with_suffix("").parts[:-1])
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[:len(package) - (node.level - 1)]
                found.add(".".join(base + ([node.module] if node.module else [])))
                found.update(".".join(base + ([node.module] if node.module else []) + [a.name])
                             for a in node.names)
            else:
                found.add(node.module)
    return found


def universe_tickers():
    universe = json.loads((ROOT / "config" / "universe.json").read_text(encoding="utf-8"))
    return {t for scope in ("market", "sector", "pairs", "asx_sector", "asx_pairs") for s in universe.get(scope, {}).get("subjects", [])
            for t in s["roles"].values()}


def test_1_calculation_layer_has_no_network_file_or_clock_access():
    banned = re.compile(r"yfinance|requests|open\(|datetime\.now|time\.time|urllib")
    for path in sources(PIPELINE / "calc"):
        hits = [line for line in path.read_text(encoding="utf-8").splitlines() if banned.search(line)]
        assert not hits, f"{path.name}: {hits}"


def test_2_layer_dependencies():
    for path in sources(PIPELINE / "collect"):
        assert not any(m.startswith(("pipeline.calc", "pipeline.sectors")) for m in imports(path)), path.name
    for path in sources(PIPELINE / "calc"):
        assert not any(m.startswith(("pipeline.collect", "pipeline.sectors", "pipeline.registry"))
                       for m in imports(path)), path.name
    for path in sources(PIPELINE / "sectors"):
        assert not any(m.startswith(("pipeline.collect", "pipeline.registry")) for m in imports(path)), path.name
    # nothing imports the orchestrator
    for path in sources(PIPELINE):
        assert "run_pipeline" not in imports(path), path.name


def test_3_only_the_orchestrator_writes_files():
    writers = re.compile(r"write_text|write_bytes|\.to_csv|\.to_json|json\.dump\(|open\(|os\.replace")
    for path in sources(PIPELINE):
        hits = [line for line in path.read_text(encoding="utf-8").splitlines() if writers.search(line)]
        assert not hits, f"{path.name}: {hits}"
    assert "write_json" in ORCHESTRATOR.read_text(encoding="utf-8")


def test_4_no_ticker_is_spelled_out_in_code():
    files = sources(PIPELINE) + [ORCHESTRATOR] + ([FRONT_END] if FRONT_END.exists() else [])
    for path in files:
        text = path.read_text(encoding="utf-8")
        for ticker in universe_tickers():
            assert not re.search(rf"""["'`]{re.escape(ticker)}["'`]""", text), f"{path.name} names {ticker}"


def test_4b_no_contract_code_is_spelled_out_in_code():
    universe = json.loads((ROOT / "config" / "universe.json").read_text(encoding="utf-8"))
    codes = {s["cftc_code"] for s in universe["cot"]["subjects"]}
    files = sources(PIPELINE) + [ORCHESTRATOR] + ([FRONT_END] if FRONT_END.exists() else [])
    for path in files:
        text = path.read_text(encoding="utf-8")
        for code in codes:
            assert code not in text, f"{path.name} names contract code {code}"


def test_5_front_end_names_no_indicator():
    if not FRONT_END.exists():
        return
    text = FRONT_END.read_text(encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "indicators.json").read_text(encoding="utf-8"))
    for iid, d in cfg["indicators"].items():
        assert iid not in text and d["calculator"] not in text, f"breadth.js names {iid}"
        for sentence in d["expert_view"] + [d["name_zh"]]:
            assert sentence not in text, f"breadth.js contains indicator copy: {sentence}"


def test_new_code_does_not_import_the_existing_scripts():
    for path in sources(PIPELINE) + [ORCHESTRATOR]:
        assert not (imports(path) & EXISTING_SCRIPTS), f"{path.name} imports {imports(path) & EXISTING_SCRIPTS}"


def test_5b_front_end_holds_no_pair_copy():
    """The ratio pairs' names and reading guides live in universe.json only."""
    if not FRONT_END.exists():
        return
    text = FRONT_END.read_text(encoding="utf-8")
    universe = json.loads((ROOT / "config" / "universe.json").read_text(encoding="utf-8"))
    copy = []
    for scope in ("pairs", "asx_pairs"):
        block = universe.get(scope, {})
        copy += list(block.get("groups", {}).values()) + list(block.get("state_conditions", {}).values())
        for s in block.get("subjects", []):
            g = s["guide"]
            copy += [s["name_zh"], g["compare"], g.get("caveat", ""), g.get("us_compare", ""), s.get("caption", "")]
            copy += list(g["states"].values())
            copy += [x for item in g.get("signals", []) for x in (item["condition"], item["meaning"])]
            assert s["id"] not in text, f"breadth.js names pair {s['id']}"
    for m in universe.get("ticker_meta", {}).values():
        copy += [m.get("name", ""), m.get("code", "")]
    for sentence in filter(None, copy):
        assert sentence not in text, f"breadth.js contains pair copy: {sentence}"
