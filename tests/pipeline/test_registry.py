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
CALCULATORS = PRICE_INDICATORS | {"cot_index"}


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


def test_shipped_config_has_the_six_price_indicators_and_three_cot_lookbacks(cfg):
    assert set(cfg[0]["indicators"]) == PRICE_INDICATORS | COT_INDICATORS
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
