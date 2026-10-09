"""Registry validation (spec B.6): the shipped config passes, and every rule
has a config that fails with an error naming the entry and the field."""
import copy
import json
from pathlib import Path

import pytest

from pipeline import registry
from pipeline.registry import RegistryError

ROOT = Path(__file__).resolve().parents[2]
INDICATORS = ROOT / "config" / "indicators.json"
UNIVERSE = ROOT / "config" / "universe.json"

PRICE_INDICATORS = {"trend_regime", "distribution_days", "equal_weight_ratio",
                    "follow_through_day", "realized_vol", "relative_strength"}
COT_INDICATORS = {"cot_index_1y", "cot_index_3y", "cot_index_6m"}
PAIR_INDICATORS = {"pair_trend", "pair_change"}
CALCULATORS = PRICE_INDICATORS | {"cot_index", "ratio_trend"}


@pytest.fixture
def cfg():
    return registry.load_json(INDICATORS), registry.load_json(UNIVERSE)


def _fails(ind, uni, entry, field):
    with pytest.raises(RegistryError) as err:
        registry.validate(ind, uni, CALCULATORS)
    assert err.value.entry == entry, str(err.value)
    assert err.value.field == field, str(err.value)
    assert entry in str(err.value) and field in str(err.value)


def test_shipped_config_is_valid(cfg):
    registry.validate(*cfg, CALCULATORS)


def test_shipped_config_has_the_six_price_indicators_three_cot_lookbacks_and_two_pair_views(cfg):
    assert set(cfg[0]["indicators"]) == PRICE_INDICATORS | COT_INDICATORS | PAIR_INDICATORS
    # the two pair entries share one calculator and must agree on when a value exists
    pairs = [cfg[0]["indicators"][i] for i in sorted(PAIR_INDICATORS)]
    assert {d["calculator"] for d in pairs} == {"ratio_trend"}
    assert len({d["min_history_days"] for d in pairs}) == 1
    strip = lambda d: {k: v for k, v in d["params"].items() if k != "history_days"}
    assert strip(pairs[0]) == strip(pairs[1])
    # one calculator, three registry entries that differ only in their parameters
    assert {cfg[0]["indicators"][i]["calculator"] for i in COT_INDICATORS} == {"cot_index"}


# ---- rule 1: required fields present, ids unique

@pytest.mark.parametrize("field", ["enabled", "name", "name_zh", "calculator", "inputs",
                                   "min_history_days", "params", "scopes", "expert_view"])
def test_rule1_missing_required_field(cfg, field):
    ind, uni = cfg
    del ind["indicators"]["trend_regime"][field]
    _fails(ind, uni, "indicators.trend_regime", field)


def test_rule1_expert_view_needs_two_to_four_sentences(cfg):
    ind, uni = cfg
    ind["indicators"]["trend_regime"]["expert_view"] = ["只有一句"]
    _fails(ind, uni, "indicators.trend_regime", "expert_view")


def test_rule1_duplicate_indicator_id(tmp_path):
    text = INDICATORS.read_text(encoding="utf-8")
    # Insert a second "trend_regime" key next to the first one.
    dup = text.replace('"indicators": {', '"indicators": {\n    "trend_regime": {},', 1)
    path = tmp_path / "indicators.json"
    path.write_text(dup, encoding="utf-8")
    with pytest.raises(RegistryError) as err:
        registry.load_json(path)
    assert err.value.field == "trend_regime"


def test_rule1_duplicate_subject_id(cfg):
    ind, uni = cfg
    uni["sector"]["subjects"][1]["id"] = "technology"
    _fails(ind, uni, "universe.sector.technology", "id")


def test_rule1_subject_without_subject_role(cfg):
    ind, uni = cfg
    del uni["sector"]["subjects"][0]["roles"]["subject"]
    _fails(ind, uni, "universe.sector.technology", "roles.subject")


# ---- rule 2: calculator exists

def test_rule2_unknown_calculator(cfg):
    ind, uni = cfg
    ind["indicators"]["realized_vol"]["calculator"] = "no_such_function"
    _fails(ind, uni, "indicators.realized_vol", "calculator")


# ---- rule 3: roles and market subjects

def test_rule3_unknown_role(cfg):
    ind, uni = cfg
    ind["indicators"]["relative_strength"]["inputs"] = ["subject", "peer"]
    _fails(ind, uni, "indicators.relative_strength", "inputs")


def test_rule3_market_subject_not_in_universe(cfg):
    ind, uni = cfg
    ind["indicators"]["trend_regime"]["scopes"]["market"]["subjects"] = ["spy", "dia"]
    _fails(ind, uni, "indicators.trend_regime", "scopes.market.subjects")


# ---- rule 4: enumerations

def test_rule4_unknown_component(cfg):
    ind, uni = cfg
    ind["indicators"]["trend_regime"]["scopes"]["sector"]["component"] = "gauge"
    _fails(ind, uni, "indicators.trend_regime", "scopes.sector.component")


def test_rule4_unknown_format(cfg):
    ind, uni = cfg
    ind["indicators"]["distribution_days"]["scopes"]["market"]["format"] = "stars"
    _fails(ind, uni, "indicators.distribution_days", "scopes.market.format")


def test_rule4_unknown_chart_type(cfg):
    ind, uni = cfg
    ind["indicators"]["realized_vol"]["detail_chart"]["type"] = "candles"
    _fails(ind, uni, "indicators.realized_vol", "detail_chart.type")


def test_rule4_unknown_tone_rule_type(cfg):
    ind, uni = cfg
    ind["indicators"]["equal_weight_ratio"]["tone_rule"]["type"] = "gradient"
    _fails(ind, uni, "indicators.equal_weight_ratio", "tone_rule.type")


def test_rule4_unknown_tone(cfg):
    ind, uni = cfg
    ind["indicators"]["trend_regime"]["tone_rule"]["map"]["BULLISH"] = "green"
    _fails(ind, uni, "indicators.trend_regime", "tone_rule.map.BULLISH")


def test_rule4_unknown_cross_section_op(cfg):
    ind, uni = cfg
    ind["indicators"]["relative_strength"]["cross_section"][0]["op"] = "zscore"
    _fails(ind, uni, "indicators.relative_strength", "cross_section[0].op")


# ---- rule 5: order unique within a scope

def test_rule5_duplicate_order_in_scope(cfg):
    ind, uni = cfg
    ind["indicators"]["distribution_days"]["scopes"]["sector"]["order"] = 20
    _fails(ind, uni, "indicators.distribution_days", "scopes.sector.order")


def test_rule5_same_order_in_different_scopes_is_fine(cfg):
    ind, uni = cfg
    ind["indicators"]["trend_regime"]["scopes"]["market"]["order"] = 20
    ind["indicators"]["distribution_days"]["scopes"]["market"]["order"] = 10
    registry.validate(ind, uni, CALCULATORS)


# ---- rule 6: default sort points at an enabled sector indicator

def test_rule6_default_sort_on_disabled_indicator(cfg):
    ind, uni = cfg
    ind["indicators"]["relative_strength"]["enabled"] = False
    _fails(ind, uni, "sector_table", "default_sort.indicator")


def test_rule6_default_sort_on_market_only_indicator(cfg):
    ind, uni = cfg
    ind["sector_table"]["default_sort"]["indicator"] = "follow_through_day"
    _fails(ind, uni, "sector_table", "default_sort.indicator")


# ---- rule 7: no banned word in user-facing text

@pytest.mark.parametrize("field,value", [
    ("name", "CupSir Trend"),
    ("name_zh", "cupsir 趨勢"),
    ("expert_view", ["CUPSIR 建議檢查", "50 日線方向是否向上"]),
    ("disclaimer", "按 CupSir 框架"),
])
def test_rule7_banned_word(cfg, field, value):
    ind, uni = cfg
    ind["indicators"]["trend_regime"][field] = value
    _fails(ind, uni, "indicators.trend_regime", field)


def test_rule7_banned_word_in_column_label(cfg):
    ind, uni = cfg
    ind["indicators"]["trend_regime"]["scopes"]["sector"]["column_label"] = "Cupsir 趨勢"
    _fails(ind, uni, "indicators.trend_regime", "scopes.sector.column_label")


def test_rule7_banned_word_in_ui_labels(cfg):
    ind, uni = cfg
    ind["ui_labels"]["expert_view_heading"] = "CupSir 建議檢查"
    _fails(ind, uni, "ui_labels", "expert_view_heading")


# ---- helpers used by the other layers

def test_enabled_indicators_respects_enabled_and_scope(cfg):
    ind, _ = cfg
    ind["indicators"]["realized_vol"]["enabled"] = False
    sector = [iid for iid, _ in registry.enabled_indicators(ind, "sector")]
    market = [iid for iid, _ in registry.enabled_indicators(ind, "market")]
    assert "realized_vol" not in sector
    assert "follow_through_day" in market and "follow_through_day" not in sector
    assert "relative_strength" in sector and "relative_strength" not in market


# ---- rules added after review: params, id shape, component per scope, value types

REQUIRED = {name: () for name in CALCULATORS}


def test_missing_param_names_the_param(cfg):
    ind, uni = cfg
    required = dict(REQUIRED, trend_regime=("fast", "mid", "slow", "slope_window", "history_days"))
    registry.validate(ind, uni, required)
    del ind["indicators"]["trend_regime"]["params"]["history_days"]
    with pytest.raises(RegistryError) as err:
        registry.validate(ind, uni, required)
    assert (err.value.entry, err.value.field) == ("indicators.trend_regime", "params.history_days")


def test_shipped_config_gives_every_calculator_its_params(cfg):
    from pipeline import calc
    registry.validate(*cfg, calc.registered())
    assert all(calc.registered()[d["calculator"]] for d in cfg[0]["indicators"].values())


@pytest.mark.parametrize("bad_id", ['x" onmouseover="1', "Trend", "9lives", "a-b"])
def test_indicator_id_must_be_a_plain_identifier(cfg, bad_id):
    ind, uni = cfg
    ind["indicators"][bad_id] = ind["indicators"].pop("realized_vol")
    _fails(ind, uni, f"indicators.{bad_id}", "")


def test_subject_id_must_be_a_plain_identifier(cfg):
    ind, uni = cfg
    uni["sector"]["subjects"][0]["id"] = "Tech Sector"
    _fails(ind, uni, "universe.sector.subjects[0]", "id")


def test_component_must_fit_its_scope(cfg):
    ind, uni = cfg
    ind["indicators"]["trend_regime"]["scopes"]["sector"]["component"] = "status_card"
    _fails(ind, uni, "indicators.trend_regime", "scopes.sector.component")


def test_wrongly_typed_values_are_config_errors_not_crashes(cfg, tmp_path):
    ind, uni = cfg
    ind["indicators"]["trend_regime"]["scopes"]["market"]["subjects"] = [["spy"]]
    _fails(ind, uni, "indicators.trend_regime", "scopes.market.subjects")
    ind, uni = registry.load_json(INDICATORS), registry.load_json(UNIVERSE)
    ind["sector_table"]["default_sort"]["indicator"] = ["relative_strength"]
    _fails(ind, uni, "sector_table", "default_sort.indicator")


def test_required_ui_labels(cfg):
    ind, uni = cfg
    del ind["ui_labels"]["na"]
    _fails(ind, uni, "ui_labels", "na")


# ---- WP2: the CFTC source, the positions role and the cot scope (guide 5.3)

def test_cot_indicator_cannot_use_a_price_role(cfg):
    ind, uni = cfg
    ind["indicators"]["cot_index_1y"]["inputs"] = ["subject"]
    _fails(ind, uni, "indicators.cot_index_1y", "inputs")


def test_price_indicator_cannot_use_the_positions_role(cfg):
    ind, uni = cfg
    ind["indicators"]["trend_regime"]["inputs"] = ["positions"]
    _fails(ind, uni, "indicators.trend_regime", "inputs")


def test_price_indicator_cannot_appear_in_the_cot_scope(cfg):
    ind, uni = cfg
    ind["indicators"]["trend_regime"]["scopes"]["cot"] = dict(ind["indicators"]["cot_index_1y"]["scopes"]["cot"], order=99)
    _fails(ind, uni, "indicators.trend_regime", "scopes.cot")


def test_unknown_source(cfg):
    ind, uni = cfg
    ind["indicators"]["cot_index_1y"]["source"] = "bloomberg"
    _fails(ind, uni, "indicators.cot_index_1y", "source")


def test_contract_code_must_be_text_to_keep_its_leading_zero(cfg):
    ind, uni = cfg
    uni["cot"]["subjects"][0]["cftc_code"] = 1602
    _fails(ind, uni, "universe.cot.wheat", "cftc_code")


def test_duplicate_contract_code(cfg):
    ind, uni = cfg
    uni["cot"]["subjects"][1]["cftc_code"] = uni["cot"]["subjects"][0]["cftc_code"]
    _fails(ind, uni, "universe.cot.soybeans", "cftc_code")


def test_cot_group_must_be_declared(cfg):
    ind, uni = cfg
    uni["cot"]["subjects"][0]["group"] = "livestock"
    _fails(ind, uni, "universe.cot.wheat", "group")


def test_cot_indicator_needs_the_cot_universe(cfg):
    ind, uni = cfg
    del uni["cot"]
    _fails(ind, uni, "indicators.cot_index_1y", "scopes.cot")


def test_chart_levels_and_y_range_shape(cfg):
    ind, uni = cfg
    ind["indicators"]["cot_index_1y"]["detail_chart"]["y_range"] = [100, 0]
    _fails(ind, uni, "indicators.cot_index_1y", "detail_chart.y_range")
    ind, uni = registry.load_json(INDICATORS), registry.load_json(UNIVERSE)
    ind["indicators"]["cot_index_1y"]["detail_chart"]["levels"] = ["80"]
    _fails(ind, uni, "indicators.cot_index_1y", "detail_chart.levels")


def test_shipped_cot_universe_has_sixteen_markets_with_distinct_text_codes(cfg):
    subjects = cfg[1]["cot"]["subjects"]
    assert len(subjects) == 16
    codes = [s["cftc_code"] for s in subjects]
    assert len(set(codes)) == 16 and all(isinstance(c, str) and len(c) == 6 for c in codes)
    assert {"043602", "001602", "067651", "13874A"} <= set(codes)


def test_contract_code_with_surrounding_spaces_is_rejected(cfg):
    ind, uni = cfg
    uni["cot"]["subjects"][0]["cftc_code"] = " 001602"
    _fails(ind, uni, "universe.cot.wheat", "cftc_code")


# ---- list view: which value an indicator shows beside each row of a tab's list

def test_shipped_config_names_the_list_values_and_both_view_labels(cfg):
    ind = cfg[0]
    shown = {(iid, scope): d["scopes"][scope]["list"]
             for iid, d in ind["indicators"].items() for scope in d["scopes"] if "list" in d["scopes"][scope]}
    assert set(shown) == {("relative_strength", "sector"), ("trend_regime", "sector"), ("cot_index_1y", "cot"),
                          ("pair_trend", "pairs"), ("pair_change", "pairs"),
                          ("relative_strength", "asx_sector"), ("trend_regime", "asx_sector"),
                          ("pair_trend", "asx_pairs"), ("pair_change", "asx_pairs")}
    assert shown[("relative_strength", "sector")]["format"] == "rank"
    for label in ("view_list", "view_table"):
        assert ind["ui_labels"][label]


@pytest.mark.parametrize("change,field", [
    (lambda item: item.pop("order"), "scopes.sector.list.order"),
    (lambda item: item.pop("value_key"), "scopes.sector.list.value_key"),
    (lambda item: item.update(format="sparkline"), "scopes.sector.list.format"),
    (lambda item: item.update(order="first"), "scopes.sector.list.order"),
])
def test_list_entry_must_be_complete(cfg, change, field):
    ind, uni = cfg
    change(ind["indicators"]["trend_regime"]["scopes"]["sector"]["list"])
    _fails(ind, uni, "indicators.trend_regime", field)


def test_list_entry_must_be_an_object(cfg):
    ind, uni = cfg
    ind["indicators"]["trend_regime"]["scopes"]["sector"]["list"] = "state"
    _fails(ind, uni, "indicators.trend_regime", "scopes.sector.list")


def test_the_market_scope_has_no_list_view(cfg):
    ind, uni = cfg
    ind["indicators"]["trend_regime"]["scopes"]["market"]["list"] = {"order": 1, "value_key": "state", "format": "state_chip"}
    _fails(ind, uni, "indicators.trend_regime", "scopes.market.list")


def test_an_indicator_without_a_list_entry_is_fine(cfg):
    ind, uni = cfg
    del ind["indicators"]["trend_regime"]["scopes"]["sector"]["list"]
    registry.validate(ind, uni, CALCULATORS)


# ---------------------------------------------------------------- pairs (spec F)

def _pair(uni, pid="xly_xlp"):
    return next(s for s in uni["pairs"]["subjects"] if s["id"] == pid)


def test_shipped_pairs_cover_three_groups_and_every_guide_names_every_state(cfg):
    block = cfg[1]["pairs"]
    assert list(block["groups"]) == ["macro", "rotation", "structure"]
    assert len(block["subjects"]) == 23
    assert {s["group"] for s in block["subjects"]} == set(block["groups"])
    for s in block["subjects"]:
        assert set(s["roles"]) == {"subject", "benchmark"}
        assert set(s["guide"]["states"]) == set(block["state_conditions"]), s["id"]
        assert s["guide"]["signals"], s["id"]


@pytest.mark.parametrize("change,entry,field", [
    (lambda s: s.pop("guide"), "universe.pairs.xly_xlp", "guide"),
    (lambda s: s["guide"].pop("compare"), "universe.pairs.xly_xlp", "guide.compare"),
    (lambda s: s["guide"]["states"].update(UP="x"), "universe.pairs.xly_xlp", "guide.states.UP"),
    (lambda s: s["guide"]["signals"].append({"condition": "x"}), "universe.pairs.xly_xlp", "guide.signals[3]"),
    (lambda s: s["guide"].update(caveat=""), "universe.pairs.xly_xlp", "guide.caveat"),
    (lambda s: s["guide"].update(compare="CupSir 說"), "universe.pairs.xly_xlp", "guide.compare"),
    (lambda s: s["roles"].pop("benchmark"), "universe.pairs.xly_xlp", "roles"),
    (lambda s: s["roles"].update(equal_weight="RSP"), "universe.pairs.xly_xlp", "roles"),
    (lambda s: s["roles"].update(benchmark=s["roles"]["subject"]), "universe.pairs.xly_xlp", "roles"),
    (lambda s: s.update(group="other"), "universe.pairs.xly_xlp", "group"),
    (lambda s: s.update(levels=["1"]), "universe.pairs.xly_xlp", "levels"),
    (lambda s: s.update(tag=""), "universe.pairs.xly_xlp", "tag"),
])
def test_pair_rules(cfg, change, entry, field):
    ind, uni = copy.deepcopy(cfg[0]), copy.deepcopy(cfg[1])
    change(_pair(uni))
    _fails(ind, uni, entry, field)


def test_pair_ids_are_unique(cfg):
    ind, uni = copy.deepcopy(cfg[0]), copy.deepcopy(cfg[1])
    uni["pairs"]["subjects"].append(copy.deepcopy(_pair(uni)))
    _fails(ind, uni, "universe.pairs.xly_xlp", "id")


def test_pairs_block_needs_state_conditions(cfg):
    ind, uni = copy.deepcopy(cfg[0]), copy.deepcopy(cfg[1])
    uni["pairs"].pop("state_conditions")
    _fails(ind, uni, "universe", "pairs.state_conditions")


def test_a_pairs_indicator_without_a_pairs_block_is_rejected(cfg):
    ind, uni = copy.deepcopy(cfg[0]), copy.deepcopy(cfg[1])
    uni.pop("pairs")
    _fails(ind, uni, "indicators.pair_trend", "scopes.pairs")


def test_the_pairs_block_is_optional_when_no_indicator_uses_it(cfg):
    ind, uni = copy.deepcopy(cfg[0]), copy.deepcopy(cfg[1])
    uni.pop("pairs")
    for iid in PAIR_INDICATORS:
        ind["indicators"].pop(iid)
    registry.validate(ind, uni, CALCULATORS)


# ---- ASX sector scope, calendars and ticker_meta (spec G.4)

def _asx_ticker(uni):
    return uni["asx_sector"]["subjects"][0]["roles"]["subject"]


def test_shipped_asx_sector_scope_has_eleven_sectors_against_one_benchmark(cfg):
    _, uni = cfg
    subjects = uni["asx_sector"]["subjects"]
    assert len(subjects) == 11
    assert len({s["roles"]["benchmark"] for s in subjects}) == 1
    assert all(set(s["roles"]) == {"subject", "benchmark"} for s in subjects)   # no equal_weight (G-Q1)


@pytest.mark.parametrize("change,entry_of,field", [
    (lambda u, t: u["ticker_meta"].pop(t), lambda u, t: f"universe.asx_sector.{u['asx_sector']['subjects'][0]['id']}", "roles.subject"),
    (lambda u, t: u["ticker_meta"][t].update(kind="etf"), lambda u, t: f"universe.ticker_meta.{t}", "kind"),
    (lambda u, t: u["ticker_meta"][t].update(calendar="lse"), lambda u, t: f"universe.ticker_meta.{t}", "calendar"),
    (lambda u, t: u["ticker_meta"][t].update(name=""), lambda u, t: f"universe.ticker_meta.{t}", "name"),
    (lambda u, t: u["ticker_meta"][t].update(name="CupSir index"), lambda u, t: f"universe.ticker_meta.{t}", "name"),
    (lambda u, t: u["calendars"]["asx"].update(tz="Sydney/Australia"), lambda u, t: "universe.calendars.asx", "tz"),
    (lambda u, t: u["calendars"]["asx"].update(rule="close"), lambda u, t: "universe.calendars.asx", "rule"),
    (lambda u, t: u["calendars"]["asx"].pop("final_after"), lambda u, t: "universe.calendars.asx", "final_after"),
    (lambda u, t: u["calendars"]["asx"].update(final_after="4:30pm"), lambda u, t: "universe.calendars.asx", "final_after"),
])
def test_asx_universe_rules(cfg, change, entry_of, field):
    ind, uni = copy.deepcopy(cfg)
    ticker = _asx_ticker(uni)
    change(uni, ticker)
    _fails(ind, uni, entry_of(uni, ticker), field)


def test_previous_day_calendar_needs_no_final_after(cfg):
    ind, uni = copy.deepcopy(cfg)
    uni["calendars"]["asx"] = {"tz": "Australia/Sydney", "rule": "previous_day"}
    registry.validate(ind, uni, CALCULATORS)


def test_asx_indicator_needs_the_asx_universe(cfg):
    ind, uni = copy.deepcopy(cfg)
    uni.pop("asx_sector")
    _fails(ind, uni, "indicators.trend_regime", "scopes.asx_sector")


def test_asx_sector_table_is_required_with_asx_indicators(cfg):
    ind, uni = copy.deepcopy(cfg)
    ind.pop("asx_sector_table")
    _fails(ind, uni, "asx_sector_table", "")


def test_asx_sector_table_must_point_at_an_asx_indicator(cfg):
    ind, uni = copy.deepcopy(cfg)
    ind["asx_sector_table"]["default_sort"]["indicator"] = "equal_weight_ratio"   # US sectors only (G-Q1)
    _fails(ind, uni, "asx_sector_table", "default_sort.indicator")


def test_us_scopes_need_no_ticker_meta(cfg):
    ind, uni = copy.deepcopy(cfg)
    asx = {t for scope in registry.ASX_SCOPES for s in uni[scope]["subjects"] for t in s["roles"].values()}
    for scope in ("market", "sector", "pairs"):
        for s in uni[scope]["subjects"]:
            for t in set(s["roles"].values()) - asx:
                uni["ticker_meta"].pop(t, None)
    registry.validate(ind, uni, CALCULATORS)


# ---- ASX pairs (spec G.6, G.7)

def _asx_pair(uni, pid):
    return next(s for s in uni["asx_pairs"]["subjects"] if s["id"] == pid)


def test_shipped_asx_pairs_have_22_entries_each_with_a_us_comparison(cfg):
    _, uni = cfg
    subjects = uni["asx_pairs"]["subjects"]
    assert len(subjects) == 22
    assert {s["group"] for s in subjects} == set(uni["asx_pairs"]["groups"])
    for s in subjects:
        assert s["guide"]["us_compare"] and set(s["guide"]["states"]) == set(uni["asx_pairs"]["state_conditions"])
    singles = [s for s in subjects if s.get("single")]
    assert [s["id"] for s in singles] == ["asx_audjpy"] and set(singles[0]["roles"]) == {"subject"}


@pytest.mark.parametrize("change,field", [
    (lambda s: s["roles"].update(benchmark="GC=F"), "roles"),        # a single series takes no denominator
    (lambda s: s.pop("caption"), "caption"),
    (lambda s: s.update(single="yes"), "single"),
    (lambda s: s["guide"].update(us_compare=""), "guide.us_compare"),
])
def test_single_series_rules(cfg, change, field):
    ind, uni = copy.deepcopy(cfg)
    change(_asx_pair(uni, "asx_audjpy"))
    _fails(ind, uni, "universe.asx_pairs.asx_audjpy", field)


def test_a_two_sided_pair_cannot_drop_its_benchmark(cfg):
    ind, uni = copy.deepcopy(cfg)
    _asx_pair(uni, "asx_xdj_xsj")["roles"].pop("benchmark")
    _fails(ind, uni, "universe.asx_pairs.asx_xdj_xsj", "roles")


def test_asx_pair_ticker_needs_ticker_meta(cfg):
    ind, uni = copy.deepcopy(cfg)
    uni["ticker_meta"].pop(_asx_pair(uni, "asx_cba_mvb")["roles"]["subject"])
    _fails(ind, uni, "universe.asx_pairs.asx_cba_mvb", "roles.subject")


def test_a_pair_never_mixes_price_indices_with_adjusted_prices(cfg):
    """Spec G.6: both sides of an ASX pair are of the same kind (futures and FX carry no dividends)."""
    _, uni = cfg
    meta = uni["ticker_meta"]
    for s in uni["asx_pairs"]["subjects"]:
        kinds = {meta[t]["kind"] for t in s["roles"].values()}
        assert len(kinds) == 1, (s["id"], kinds)
