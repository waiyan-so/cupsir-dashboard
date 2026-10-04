"""Orchestrator and sector layer end to end, offline (spec sections 2, 6 and 8)."""
import json
import shutil
from pathlib import Path

import pytest

import run_pipeline
from pipeline import calc
from pipeline.calc._math import sma
from helpers import ROOT

ENVELOPE = set(calc.RESULT_KEYS)
MARKET, SECTORS, COT = "market_breadth.json", "sectors.json", "cot.json"
NEW_FILES = (MARKET, SECTORS, COT)


def run(tmp_path, *argv, data=None):
    data = data or tmp_path / "data"
    code = run_pipeline.main(list(argv), data_dir=data)
    return code, data


def load(data, name):
    return json.loads((data / name).read_text(encoding="utf-8"))


def registry_with(tmp_path, change):
    """A copy of the shipped registry with `change(cfg)` applied, for --registry."""
    cfg = json.loads((ROOT / "config" / "indicators.json").read_text(encoding="utf-8"))
    change(cfg)
    path = tmp_path / "indicators_test.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return str(path)


# ---- normal run

def test_offline_run_writes_both_files_with_the_documented_shape(tmp_path, offline_dir):
    code, data = run(tmp_path, "--offline", str(offline_dir))
    assert code == 0
    market, sector = load(data, MARKET), load(data, SECTORS)

    for payload in (market, sector):
        assert payload["schema_version"] == 2
        assert payload["updated_at"].endswith(" UTC") and len(payload["updated_at"]) == 20
        assert payload["meta"]["ui_labels"]["expert_view_heading"] == "Expert's view"

    # market: meta drives everything the page needs; results are indicator -> subject -> Result
    meta = market["meta"]
    assert [s["id"] for s in meta["subjects"]] == ["spy", "qqq"]
    assert [i["id"] for i in meta["indicators"]] == \
        ["trend_regime", "distribution_days", "equal_weight_ratio", "follow_through_day"]
    assert [i["order"] for i in meta["indicators"]] == [10, 20, 30, 40]
    for ind in meta["indicators"]:
        assert {"id", "name", "name_zh", "subjects", "component", "order", "value_key", "format",
                "detail_chart", "expert_view", "disclaimer"} <= set(ind)
        assert not {"params", "notes", "calculator", "inputs", "min_history_days", "tone_rule"} & set(ind)
        for sid in ind["subjects"]:
            result = market["results"][ind["id"]][sid]
            assert set(result) == ENVELOPE and result["status"] == "ok"

    # sectors: one row per sector, one Result per sector indicator
    assert [i["id"] for i in sector["meta"]["indicators"]] == \
        ["relative_strength", "trend_regime", "distribution_days", "equal_weight_ratio", "realized_vol"]
    assert sector["meta"]["default_sort"]["value_key"] == "return_63d_excess_pct"
    assert sector["meta"]["tie_break"]["value_key"] == "return_21d_excess_pct"
    assert len(sector["rows"]) == 11
    for row in sector["rows"]:
        assert set(row) == {"id", "name_zh", "tickers", "results"}
        assert set(row["tickers"]) == {"subject", "equal_weight", "benchmark"}
        assert set(row["results"]) == {i["id"] for i in sector["meta"]["indicators"]}
        for result in row["results"].values():
            assert set(result) == ENVELOPE and result["status"] == "ok"
            assert result["data_date"] == "2026-10-02"


def test_only_the_three_new_files_are_written(tmp_path, offline_dir):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data", data)
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    code, _ = run(tmp_path, "--offline", str(offline_dir), data=data)
    assert code == 0
    after = {p.name: p.read_bytes() for p in data.iterdir()}
    assert set(after) - set(before) <= set(NEW_FILES)
    for name, content in before.items():
        if name not in NEW_FILES:
            assert after[name] == content, f"{name} was modified"


def test_two_runs_on_the_same_input_differ_only_in_updated_at(tmp_path, offline_dir):
    _, first = run(tmp_path, "--offline", str(offline_dir), data=tmp_path / "a")
    _, second = run(tmp_path, "--offline", str(offline_dir), data=tmp_path / "b")
    for name in NEW_FILES:
        a, b = load(first, name), load(second, name)
        a.pop("updated_at"), b.pop("updated_at")
        assert a == b


def test_ranks_follow_the_63_day_excess_return(tmp_path, offline_dir):
    _, data = run(tmp_path, "--offline", str(offline_dir))
    values = [row["results"]["relative_strength"]["values"] for row in load(data, SECTORS)["rows"]]
    by_rank = sorted(values, key=lambda v: v["rank_by_63d"])
    assert [v["rank_by_63d"] for v in by_rank] == list(range(1, 12))
    returns = [v["return_63d_excess_pct"] for v in by_rank]
    assert returns == sorted(returns, reverse=True)


# ---- failures stay local

def _sector(payload, sector_id):
    return next(r for r in payload["rows"] if r["id"] == sector_id)


def test_missing_sector_etf_only_blanks_that_sector(tmp_path, offline_dir):
    row_before = _sector(load(run(tmp_path, "--offline", str(offline_dir), data=tmp_path / "ref")[1], SECTORS),
                         "financials")
    target = _sector(load(tmp_path / "ref", SECTORS), "technology")["tickers"]["subject"]
    (offline_dir / "prices" / f"{target}.csv").unlink()
    code, data = run(tmp_path, "--offline", str(offline_dir))
    assert code == 0
    sector = load(data, SECTORS)
    tech = _sector(sector, "technology")["results"]
    assert all(r["status"] == "na" and r["reason"] == "fetch_failed" for r in tech.values())
    assert all(r["values"] == {} and r["history"] == [] and r["tone"] is None for r in tech.values())
    others = [r for r in sector["rows"] if r["id"] != "technology"]
    assert all(res["status"] == "ok" for r in others for res in r["results"].values())
    # ten sectors are ranked 1..10; the failed one has no rank
    assert sorted(r["results"]["relative_strength"]["values"]["rank_by_63d"] for r in others) == list(range(1, 11))
    # a sector that was not touched keeps its numbers (apart from its rank)
    fin = _sector(sector, "financials")["results"]
    assert fin["trend_regime"] == row_before["results"]["trend_regime"]
    assert load(data, MARKET)["results"]["trend_regime"]["spy"]["status"] == "ok"


def test_missing_equal_weight_etf_only_blanks_the_ratio(tmp_path, offline_dir):
    ref = load(run(tmp_path, "--offline", str(offline_dir), data=tmp_path / "ref")[1], SECTORS)
    target = _sector(ref, "energy")["tickers"]["equal_weight"]
    (offline_dir / "prices" / f"{target}.csv").unlink()
    _, data = run(tmp_path, "--offline", str(offline_dir))
    energy = _sector(load(data, SECTORS), "energy")["results"]
    assert energy["equal_weight_ratio"]["reason"] == "fetch_failed"
    assert all(r["status"] == "ok" for iid, r in energy.items() if iid != "equal_weight_ratio")


def test_short_history_gives_insufficient_history_for_long_lookbacks_only(tmp_path, offline_dir):
    ref = load(run(tmp_path, "--offline", str(offline_dir), data=tmp_path / "ref")[1], SECTORS)
    target = _sector(ref, "utilities")["tickers"]["subject"]
    path = offline_dir / "prices" / f"{target}.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([lines[0]] + lines[-100:]) + "\n", encoding="utf-8")     # keep 100 days
    _, data = run(tmp_path, "--offline", str(offline_dir))
    util = _sector(load(data, SECTORS), "utilities")["results"]
    assert util["realized_vol"]["reason"] == "insufficient_history"       # needs 273
    assert util["trend_regime"]["reason"] == "insufficient_history"       # needs 205
    assert util["relative_strength"]["status"] == "ok"                    # needs 64
    assert util["distribution_days"]["status"] == "ok"                    # needs 30


def test_no_data_at_all_exits_1_and_keeps_the_previous_files(tmp_path, offline_dir):
    code, data = run(tmp_path, "--offline", str(offline_dir))
    before = {n: (data / n).read_bytes() for n in (MARKET, SECTORS)}
    empty = tmp_path / "empty"
    empty.mkdir()
    code, _ = run(tmp_path, "--offline", str(empty), data=data)
    assert code == 1
    assert {n: (data / n).read_bytes() for n in (MARKET, SECTORS)} == before
    assert not list(data.glob("*.tmp"))


def test_invalid_config_exits_2_and_writes_nothing(tmp_path, offline_dir):
    bad = registry_with(tmp_path, lambda cfg: cfg["indicators"]["trend_regime"].pop("calculator"))
    code, data = run(tmp_path, "--offline", str(offline_dir), "--registry", bad)
    assert code == 2
    assert not data.exists()


def test_dry_run_writes_nothing(tmp_path, offline_dir):
    code, data = run(tmp_path, "--offline", str(offline_dir), "--dry-run")
    assert code == 0
    assert not data.exists()


def test_dry_run_without_data_exits_1(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    code, data = run(tmp_path, "--offline", str(empty), "--dry-run")
    assert code == 1 and not data.exists()


# ---- registry-driven behaviour

def test_disabled_indicator_disappears_and_the_rest_is_unchanged(tmp_path, offline_dir):
    ref = run(tmp_path, "--offline", str(offline_dir), data=tmp_path / "ref")[1]
    off = registry_with(tmp_path, lambda cfg: cfg["indicators"]["distribution_days"].update(enabled=False))
    code, data = run(tmp_path, "--offline", str(offline_dir), "--registry", off)
    assert code == 0
    market, sector = load(data, MARKET), load(data, SECTORS)
    assert "distribution_days" not in [i["id"] for i in market["meta"]["indicators"]]
    assert "distribution_days" not in market["results"]
    assert "distribution_days" not in [i["id"] for i in sector["meta"]["indicators"]]
    assert all("distribution_days" not in r["results"] for r in sector["rows"])
    ref_market = load(ref, MARKET)
    for iid in market["results"]:
        assert market["results"][iid] == ref_market["results"][iid]


@calc.calculator("price_vs_ma")
def _price_vs_ma(frames, params):
    """Spec B.7 demo 1 calculator. Lives in this test only: the demo indicators are not shipped."""
    close = frames["subject"]["close"]
    ma = sma(close, params["window"])
    distance = (close.iloc[-1] / ma.iloc[-1] - 1) * 100
    return {"state": "ABOVE" if distance > 0 else "BELOW",
            "values": {"close": float(close.iloc[-1]), "ma": float(ma.iloc[-1]),
                       "distance_pct": round(float(distance), 2)},
            "history": [], "events": []}


SECTOR_EXT_50D = {
    "enabled": True,
    "name": "Extension from 50-day MA", "name_zh": "距離 50 日線",
    "calculator": "price_vs_ma", "inputs": ["subject"],
    "min_history_days": 50, "params": {"window": 50},
    "tone_rule": {"type": "sign", "key": "distance_pct"},
    "scopes": {"sector": {"component": "table_column", "order": 60, "column_label": "距離 50 日線",
                          "value_key": "distance_pct", "format": "signed_pct"}},
    "expert_view": ["板塊是否過度偏離 50 日線", "偏離收窄時趨勢狀態有否改變"],
    "disclaimer": None,
}


def test_a6_rule_6_adding_a_registry_entry_adds_a_sector_column(tmp_path, offline_dir):
    """Spec B.7 demo 2: only a registry entry is added; no pipeline or front-end code changes."""
    extended = registry_with(tmp_path, lambda cfg: cfg["indicators"].update(sector_ext_50d=SECTOR_EXT_50D))
    code, data = run(tmp_path, "--offline", str(offline_dir), "--registry", extended)
    assert code == 0
    sector = load(data, SECTORS)
    columns = sector["meta"]["indicators"]
    assert columns[-1]["id"] == "sector_ext_50d" and columns[-1]["column_label"] == "距離 50 日線"
    assert len(columns) == 6
    for row in sector["rows"]:
        result = row["results"]["sector_ext_50d"]
        assert result["status"] == "ok" and result["state"] in ("ABOVE", "BELOW")
        assert result["tone"] == ("positive" if result["values"]["distance_pct"] > 0 else "negative")
    assert "sector_ext_50d" not in load(data, MARKET)["results"]


def test_exit_code_from_the_command_line(tmp_path):
    import subprocess
    import sys
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_pipeline.py"),
                           "--offline", str(empty), "--dry-run"], capture_output=True, text=True)
    assert proc.returncode == 1
    assert "::error::" in proc.stdout


# ---- added after review

def test_registry_key_that_the_results_do_not_have_exits_2(tmp_path, offline_dir):
    # value_key left behind after a params change: window 25 -> 30 renames count_25d to count_30d
    stale = registry_with(tmp_path, lambda cfg: cfg["indicators"]["distribution_days"]["params"].update(window=30))
    code, data = run(tmp_path, "--offline", str(offline_dir), "--registry", stale)
    assert code == 2 and not data.exists()


def test_chart_series_that_the_history_does_not_have_exits_2(tmp_path, offline_dir):
    stale = registry_with(tmp_path, lambda cfg: cfg["indicators"]["realized_vol"]["detail_chart"].update(series=["vol"]))
    code, data = run(tmp_path, "--offline", str(offline_dir), "--registry", stale)
    assert code == 2 and not data.exists()


def test_one_output_failing_keeps_its_old_file_and_still_writes_the_other(tmp_path, offline_dir):
    code, data = run(tmp_path, "--offline", str(offline_dir))
    market_before = (data / MARKET).read_bytes()
    sector_before = load(data, SECTORS)
    for subject in load(data, MARKET)["meta"]["subjects"]:
        (offline_dir / "prices" / f"{subject['ticker']}.csv").unlink()
    code, _ = run(tmp_path, "--offline", str(offline_dir), data=data)
    assert code == 0
    assert (data / MARKET).read_bytes() == market_before            # every market cell failed: old file kept
    sector_after = load(data, SECTORS)
    assert sector_after["rows"][0]["results"]["trend_regime"]["status"] == "ok"
    assert sector_after["rows"][0]["results"]["relative_strength"]["reason"] == "fetch_failed"   # benchmark gone
    assert sector_after["updated_at"] >= sector_before["updated_at"]


def test_scope_with_no_enabled_indicator_gets_an_empty_file_not_a_failure(tmp_path, offline_dir):
    def only_market(cfg):
        for d in cfg["indicators"].values():
            if "market" in d["scopes"]:
                d["scopes"].pop("sector", None)      # keep it for the market tab only
            else:
                d["enabled"] = False                 # sector-only indicator: switch it off
    code, data = run(tmp_path, "--offline", str(offline_dir), "--registry", registry_with(tmp_path, only_market))
    assert code == 0
    sector = load(data, SECTORS)
    assert sector["meta"]["indicators"] == [] and all(r["results"] == {} for r in sector["rows"])
    assert load(data, MARKET)["results"]["trend_regime"]["spy"]["status"] == "ok"


# ---- WP2: COT scope (implementation guide section 5)

def test_cot_file_shape(tmp_path, offline_dir):
    code, data = run(tmp_path, "--offline", str(offline_dir))
    assert code == 0
    cot = load(data, COT)
    assert cot["schema_version"] == 2 and set(cot) == {"schema_version", "updated_at", "meta", "rows"}
    meta = cot["meta"]
    assert [i["id"] for i in meta["indicators"]] == ["cot_index_1y", "cot_index_3y", "cot_index_6m"]
    assert meta["default_sort"] is None                      # default order = the order in universe.json
    assert meta["groups"] == {"agriculture": "農產品", "energy": "能源", "metals": "金屬", "financial": "金融"}
    assert meta["ui_labels"]["tab_cot"] == "COT 持倉"
    for ind in meta["indicators"]:
        assert ind["detail_chart"] == {"type": "line", "series": ["cot_index", "sentiment_index"],
                                       "levels": [80, 20], "y_range": [0, 100]}
        assert not {"params", "notes", "calculator", "source", "inputs"} & set(ind)
    universe = json.loads((ROOT / "config" / "universe.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in cot["rows"]] == [s["id"] for s in universe["cot"]["subjects"]]
    assert len(cot["rows"]) == 16
    for row in cot["rows"]:
        assert set(row) == {"id", "name_zh", "group", "cftc", "results"}
        assert set(row["cftc"]) == {"code", "name", "rows"} and row["cftc"]["rows"] == 260
        for result in row["results"].values():
            assert set(result) == ENVELOPE and result["status"] == "ok"
            assert result["data_date"] == "2026-09-29"
            assert len(result["history"]) == 52


def test_cot_market_with_short_history_blanks_only_the_long_lookback(tmp_path, offline_dir):
    cot_before = load(run(tmp_path, "--offline", str(offline_dir), data=tmp_path / "ref")[1], COT)
    code_of = {r["id"]: r["cftc"]["code"] for r in cot_before["rows"]}
    path = offline_dir / "cftc" / f"{code_of['gold']}.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([lines[0]] + lines[-100:]) + "\n", encoding="utf-8")     # 100 weeks
    _, data = run(tmp_path, "--offline", str(offline_dir))
    gold = next(r for r in load(data, COT)["rows"] if r["id"] == "gold")
    assert gold["results"]["cot_index_3y"]["reason"] == "insufficient_history"           # needs 156 rows
    assert gold["results"]["cot_index_1y"]["status"] == "ok"
    assert gold["results"]["cot_index_6m"]["status"] == "ok"
    assert gold["cftc"]["rows"] == 100


def test_cftc_down_keeps_the_old_cot_file_and_still_writes_the_other_two(tmp_path, offline_dir):
    code, data = run(tmp_path, "--offline", str(offline_dir))
    cot_before = (data / COT).read_bytes()
    stamp = load(data, SECTORS)["updated_at"]
    shutil.rmtree(offline_dir / "cftc")
    (data / MARKET).unlink()
    code, _ = run(tmp_path, "--offline", str(offline_dir), data=data)
    assert code == 0
    assert (data / COT).read_bytes() == cot_before
    assert (data / MARKET).exists() and load(data, SECTORS)["updated_at"] >= stamp


def test_prices_down_still_writes_the_cot_file(tmp_path, offline_dir):
    shutil.rmtree(offline_dir / "prices")
    code, data = run(tmp_path, "--offline", str(offline_dir))
    assert code == 0
    assert (data / COT).exists() and not (data / MARKET).exists() and not (data / SECTORS).exists()


def test_adding_a_cot_market_needs_only_a_universe_entry(tmp_path, offline_dir):
    """Guide 5.6: a new market is one line in universe.json - no .py or .js change."""
    config = tmp_path / "config"
    shutil.copytree(ROOT / "config", config)
    universe = json.loads((config / "universe.json").read_text(encoding="utf-8"))
    universe["cot"]["subjects"].append({"id": "silver", "name_zh": "白銀", "group": "metals",
                                        "cftc_code": "084691", "cftc_name": "SILVER - COMMODITY EXCHANGE INC."})
    (config / "universe.json").write_text(json.dumps(universe, ensure_ascii=False), encoding="utf-8")
    source = offline_dir / "cftc" / f"{universe['cot']['subjects'][0]['cftc_code']}.csv"
    shutil.copy(source, offline_dir / "cftc" / "084691.csv")
    code = run_pipeline.main(["--offline", str(offline_dir)], data_dir=tmp_path / "data", config_dir=config)
    assert code == 0
    rows = load(tmp_path / "data", COT)["rows"]
    assert len(rows) == 17 and rows[-1]["id"] == "silver"
    assert all(r["status"] == "ok" for r in rows[-1]["results"].values())


def test_cot_results_do_not_touch_dashboard_json(tmp_path, offline_dir):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data", data)
    before = (data / "dashboard.json").read_bytes()
    run(tmp_path, "--offline", str(offline_dir), data=data)
    assert (data / "dashboard.json").read_bytes() == before


# ---- added after the WP2 review

def _stores(offline_dir):
    """The two stores an online run would get, built from the offline files."""
    from conftest import all_cftc_codes, all_tickers
    from pipeline.collect import fixtures
    return fixtures.load_prices(offline_dir, all_tickers()), fixtures.load_positions(offline_dir, all_cftc_codes())


def test_an_adapter_that_raises_does_not_stop_the_other_source(tmp_path, offline_dir):
    prices_store, _ = _stores(offline_dir)

    def broken(codes):
        raise RuntimeError("unexpected")

    code = run_pipeline.main([], data_dir=tmp_path / "data", fetch=lambda t: prices_store, fetch_cftc=broken)
    assert code == 0
    assert (tmp_path / "data" / MARKET).exists() and (tmp_path / "data" / SECTORS).exists()
    assert not (tmp_path / "data" / COT).exists()


def test_market_name_that_differs_from_the_config_is_warned_about(tmp_path, offline_dir, capsys):
    prices_store, positions = _stores(offline_dir)
    universe = json.loads((ROOT / "config" / "universe.json").read_text(encoding="utf-8"))
    gold = next(s for s in universe["cot"]["subjects"] if s["id"] == "gold")
    positions.names = {s["cftc_code"]: s["cftc_name"].lower() for s in universe["cot"]["subjects"]}   # case differs: fine
    positions.names[gold["cftc_code"]] = "SILVER - COMMODITY EXCHANGE INC."
    code = run_pipeline.main([], data_dir=tmp_path / "data", fetch=lambda t: prices_store, fetch_cftc=lambda c: positions)
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("is named") == 1 and "cot / gold" in out and "SILVER" in out


def test_nothing_computed_writes_nothing_even_when_a_scope_is_switched_off(tmp_path, offline_dir):
    def cot_off(cfg):
        for d in cfg["indicators"].values():
            if "cot" in d["scopes"]:
                d["enabled"] = False
    shutil.rmtree(offline_dir / "prices")
    code, data = run(tmp_path, "--offline", str(offline_dir), "--registry", registry_with(tmp_path, cot_off))
    assert code == 1 and not data.exists()
