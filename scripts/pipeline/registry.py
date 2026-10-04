"""
Indicator registry: load and validate config/indicators.json and
config/universe.json (spec B.1-B.6).

Validation runs at the start of every pipeline run. The first rule that
fails raises RegistryError naming the entry and the field; the orchestrator
then stops without writing any output.

The names allowed for roles, components, formats, chart types, tone rules and
cross-section ops live here, in one place. web/breadth.js has a renderer for
every component / format / chart type listed below - adding a name here
without adding its renderer there only produces a console warning in the
browser, never a broken page.
"""
import json
import re
from pathlib import Path

# Each data source has its own roles and its own scopes (guide 5.3, S2-S5).
SOURCES = ("prices", "cftc")
DEFAULT_SOURCE = "prices"
ROLES_OF_SOURCE = {"prices": ("subject", "equal_weight", "benchmark"), "cftc": ("positions",)}
SCOPES_OF_SOURCE = {"prices": ("market", "sector"), "cftc": ("cot",)}
ROLES = tuple(role for roles in ROLES_OF_SOURCE.values() for role in roles)
SCOPES = ("market", "sector", "cot")
PRICE_SCOPES = SCOPES_OF_SOURCE["prices"]
COT_SCOPE = "cot"
COMPONENTS = ("status_card", "table_column")
# Where each component can appear: cards on the market tab, columns in a table.
COMPONENT_OF_SCOPE = {"market": "status_card", "sector": "table_column", "cot": "table_column"}
FORMATS = ("state_chip", "count", "pct", "signed_pct", "percentile", "number")
CHART_TYPES = ("line", "price_with_ma", "line_with_markers")
TONE_RULE_TYPES = ("state_map", "sign", "bands")
TONES = ("positive", "warning", "negative")
CROSS_SECTION_OPS = ("rank",)
SORT_DIRS = ("asc", "desc")

# Text that must not name any individual trader (spec B.5).
BANNED_WORDS = ("cupsir",)

EXPERT_VIEW_MIN = 2
EXPERT_VIEW_MAX = 4

# Ids end up in file names, JSON keys and HTML attributes.
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
REQUIRED_LABELS = ("na", "expert_view_heading")


class RegistryError(Exception):
    """A config rule failed. `entry` and `field` say where."""

    def __init__(self, entry, field, message):
        self.entry = entry
        self.field = field
        self.message = message
        super().__init__(f"{entry}.{field}: {message}" if field else f"{entry}: {message}")


# ---------------------------------------------------------------- loading

def _reject_duplicate_keys(source):
    def hook(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                raise RegistryError(source, key, "鍵重複出現（id 必須唯一）")
            seen.add(key)
        return dict(pairs)
    return hook


def load_json(path):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise RegistryError(path.name, "", f"讀不到檔案：{e}") from e
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys(path.name))
    except json.JSONDecodeError as e:
        raise RegistryError(path.name, "", f"不是有效的 JSON：{e}") from e


def load(indicators_path, universe_path, calculators):
    """Read both config files, validate them, return (indicators_cfg, universe_cfg)."""
    indicators_cfg = load_json(indicators_path)
    universe_cfg = load_json(universe_path)
    try:
        validate(indicators_cfg, universe_cfg, calculators)
    except (TypeError, KeyError, AttributeError) as e:
        # A value of the wrong shape somewhere the rules did not anticipate.
        raise RegistryError("config", "", f"結構不正確：{type(e).__name__}: {e}") from e
    return indicators_cfg, universe_cfg


# ---------------------------------------------------------------- helpers

def _need(cond, entry, field, message):
    if not cond:
        raise RegistryError(entry, field, message)


def _is_str(v):
    return isinstance(v, str) and v.strip() != ""


def _is_id(v):
    return isinstance(v, str) and ID_PATTERN.match(v) is not None


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_text(entry, field, value):
    """Rule 7: no banned word in any text shown to the user."""
    texts = value if isinstance(value, list) else [value]
    for t in texts:
        if isinstance(t, str):
            low = t.lower()
            for word in BANNED_WORDS:
                _need(word not in low, entry, field, f"文字不可包含「{word}」（不分大小寫）")


def enabled_indicators(indicators_cfg, scope=None):
    """[(id, definition)] of enabled indicators, optionally only those shown in `scope`."""
    out = []
    for iid, d in indicators_cfg.get("indicators", {}).items():
        if not d.get("enabled"):
            continue
        if scope is not None and scope not in d.get("scopes", {}):
            continue
        out.append((iid, d))
    return out


def subjects(universe_cfg, scope):
    return universe_cfg.get(scope, {}).get("subjects", [])


# ---------------------------------------------------------------- universe

def _validate_cot_universe(universe_cfg):
    """The cot scope is optional. Its subjects carry a CFTC contract market code, not tickers."""
    block = universe_cfg.get(COT_SCOPE)
    if block is None:
        return
    _need(isinstance(block, dict) and isinstance(block.get("subjects"), list),
          "universe", f"{COT_SCOPE}.subjects", "必須是清單")
    groups = block.get("groups")
    _need(isinstance(groups, dict) and groups and all(_is_str(v) for v in groups.values()),
          "universe", f"{COT_SCOPE}.groups", "必填，「類別 id: 顯示名稱」")
    seen_ids, seen_codes = set(), set()
    for i, s in enumerate(block["subjects"]):
        where = f"universe.{COT_SCOPE}.subjects[{i}]"
        _need(isinstance(s, dict), where, "", "必須是物件")
        _need(_is_id(s.get("id")), where, "id", "必填，只可以用小寫英文字母、數字和底線")
        where = f"universe.{COT_SCOPE}.{s['id']}"
        _need(s["id"] not in seen_ids, where, "id", "id 重複")
        seen_ids.add(s["id"])
        _need(_is_str(s.get("name_zh")), where, "name_zh", "必填")
        _check_text(where, "name_zh", s["name_zh"])
        _need(isinstance(s.get("group"), str) and s["group"] in groups, where, "group",
              f"只可以是 {list(groups)}")
        # Codes can start with a zero, so they must stay text: as a number the zero is lost.
        _need(_is_str(s.get("cftc_code")), where, "cftc_code", "必填，而且必須是字串（保留前導零）")
        _need(s["cftc_code"] == s["cftc_code"].strip(), where, "cftc_code", "前後不可有空白")
        _need(s["cftc_code"] not in seen_codes, where, "cftc_code", "合約代碼重複")
        seen_codes.add(s["cftc_code"])
        _need(_is_str(s.get("cftc_name")), where, "cftc_name", "必填")


def validate_universe(universe_cfg):
    _need(isinstance(universe_cfg, dict), "universe", "", "頂層必須是物件")
    _validate_cot_universe(universe_cfg)
    for scope in PRICE_SCOPES:
        block = universe_cfg.get(scope)
        _need(isinstance(block, dict) and isinstance(block.get("subjects"), list),
              "universe", f"{scope}.subjects", "必須是清單")
        seen = set()
        for i, s in enumerate(block["subjects"]):
            where = f"universe.{scope}.subjects[{i}]"
            _need(isinstance(s, dict), where, "", "必須是物件")
            _need(_is_id(s.get("id")), where, "id", "必填，只可以用小寫英文字母、數字和底線")
            where = f"universe.{scope}.{s['id']}"
            _need(s["id"] not in seen, where, "id", "id 重複")
            seen.add(s["id"])
            _need(_is_str(s.get("name_zh")), where, "name_zh", "必填")
            _check_text(where, "name_zh", s["name_zh"])
            roles = s.get("roles")
            _need(isinstance(roles, dict) and roles, where, "roles", "必填，而且不可為空")
            for role, ticker in roles.items():
                _need(role in ROLES_OF_SOURCE["prices"], where, f"roles.{role}",
                      f"角色名只可以是 {list(ROLES_OF_SOURCE['prices'])}")
                _need(_is_str(ticker), where, f"roles.{role}", "ticker 必須是非空字串")
            _need("subject" in roles, where, "roles.subject", "每個標的至少要有 subject 角色")


# ---------------------------------------------------------------- indicators

def _validate_tone_rule(entry, rule):
    _need(isinstance(rule, dict), entry, "tone_rule", "必須是物件")
    rtype = rule.get("type")
    _need(rtype in TONE_RULE_TYPES, entry, "tone_rule.type", f"只可以是 {list(TONE_RULE_TYPES)}")
    if rtype == "state_map":
        m = rule.get("map")
        _need(isinstance(m, dict) and m, entry, "tone_rule.map", "必填")
        for state, tone in m.items():
            _need(tone in TONES, entry, f"tone_rule.map.{state}", f"顏色只可以是 {list(TONES)}")
    elif rtype == "sign":
        _need(_is_str(rule.get("key")), entry, "tone_rule.key", "必填")
    elif rtype == "bands":
        _need(_is_str(rule.get("key")), entry, "tone_rule.key", "必填")
        bands = rule.get("bands")
        _need(isinstance(bands, list) and bands, entry, "tone_rule.bands", "必填")
        last = None
        for i, band in enumerate(bands):
            ok = isinstance(band, list) and len(band) == 2 and _is_num(band[0]) and band[1] in TONES
            _need(ok, entry, f"tone_rule.bands[{i}]", f"格式是 [上限, 顏色]，顏色只可以是 {list(TONES)}")
            _need(last is None or band[0] > last, entry, f"tone_rule.bands[{i}]", "上限必須由小至大")
            last = band[0]


def _validate_scope(entry, scope, block, universe_cfg):
    field = f"scopes.{scope}"
    _need(isinstance(block, dict), entry, field, "必須是物件")
    _need(block.get("component") in COMPONENTS, entry, f"{field}.component", f"只可以是 {list(COMPONENTS)}")
    _need(block["component"] == COMPONENT_OF_SCOPE[scope], entry, f"{field}.component",
          f"{scope} 範圍只可以用 {COMPONENT_OF_SCOPE[scope]}")
    _need(block.get("format") in FORMATS, entry, f"{field}.format", f"只可以是 {list(FORMATS)}")
    _need(_is_int(block.get("order")), entry, f"{field}.order", "必填，整數")
    _need(_is_str(block.get("value_key")), entry, f"{field}.value_key", "必填")
    if "secondary_key" in block:
        _need(_is_str(block["secondary_key"]), entry, f"{field}.secondary_key", "必須是非空字串")
    if "secondary_format" in block:
        _need(block["secondary_format"] in FORMATS, entry, f"{field}.secondary_format",
              f"只可以是 {list(FORMATS)}")
    if "sort_order" in block:
        so = block["sort_order"]
        _need(isinstance(so, list) and so and all(_is_str(x) for x in so), entry,
              f"{field}.sort_order", "必須是非空的字串清單")
    if scope == "market":
        subs = block.get("subjects")
        _need(isinstance(subs, list) and subs, entry, f"{field}.subjects", "必填，而且不可為空")
        known = {s["id"] for s in subjects(universe_cfg, "market")}
        for sid in subs:
            _need(isinstance(sid, str) and sid in known, entry, f"{field}.subjects",
                  f"「{sid}」不在 universe.json 的 market 範圍")
    else:
        _need(_is_str(block.get("column_label")), entry, f"{field}.column_label", "必填")
        _check_text(entry, f"{field}.column_label", block["column_label"])
    if scope == COT_SCOPE:
        _need(universe_cfg.get(COT_SCOPE) is not None, entry, field, "universe.json 沒有 cot 範圍")


def _validate_indicator(iid, d, universe_cfg, calculators):
    entry = f"indicators.{iid}"
    _need(_is_id(iid), entry, "", "指標 id 只可以用小寫英文字母、數字和底線")
    _need(isinstance(d, dict), entry, "", "必須是物件")

    # Rule 1: required fields.
    _need(isinstance(d.get("enabled"), bool), entry, "enabled", "必填，true 或 false")
    for key in ("name", "name_zh", "calculator"):
        _need(_is_str(d.get(key)), entry, key, "必填")
    _need(isinstance(d.get("inputs"), list) and d["inputs"], entry, "inputs", "必填，而且不可為空")
    _need(_is_int(d.get("min_history_days")) and d["min_history_days"] >= 1, entry,
          "min_history_days", "必填，正整數")
    _need(isinstance(d.get("params"), dict), entry, "params", "必填")
    _need(isinstance(d.get("scopes"), dict) and d["scopes"], entry, "scopes", "必填，至少一個範圍")
    ev = d.get("expert_view")
    _need(isinstance(ev, list) and EXPERT_VIEW_MIN <= len(ev) <= EXPERT_VIEW_MAX
          and all(_is_str(x) for x in ev), entry, "expert_view",
          f"必填，{EXPERT_VIEW_MIN} 至 {EXPERT_VIEW_MAX} 句")

    # Rule 2: calculator is registered in the calculation layer.
    _need(d["calculator"] in calculators, entry, "calculator",
          f"「{d['calculator']}」未在計算層登記；已登記：{sorted(calculators)}")
    for key in calculators[d["calculator"]]:
        _need(key in d["params"], entry, f"params.{key}", "這個計算函式需要此參數")

    # Rule 3: roles. Which roles and scopes are allowed depends on the data source.
    source = d.get("source", DEFAULT_SOURCE)
    _need(source in SOURCES, entry, "source", f"只可以是 {list(SOURCES)}")
    for role in d["inputs"]:
        _need(role in ROLES, entry, "inputs", f"「{role}」不是角色名；只可以是 {list(ROLES)}")
        _need(role in ROLES_OF_SOURCE[source], entry, "inputs",
              f"來源 {source} 的角色只可以是 {list(ROLES_OF_SOURCE[source])}")

    # Rules 3 and 4: scopes.
    for scope, block in d["scopes"].items():
        _need(scope in SCOPES, entry, f"scopes.{scope}", f"範圍只可以是 {list(SCOPES)}")
        _need(scope in SCOPES_OF_SOURCE[source], entry, f"scopes.{scope}",
              f"來源 {source} 的範圍只可以是 {list(SCOPES_OF_SOURCE[source])}")
        _validate_scope(entry, scope, block, universe_cfg)

    # Rule 4: the remaining enumerations.
    if d.get("tone_rule") is not None:
        _validate_tone_rule(entry, d["tone_rule"])
    chart = d.get("detail_chart")
    if chart is not None:
        _need(isinstance(chart, dict), entry, "detail_chart", "必須是物件或 null")
        _need(chart.get("type") in CHART_TYPES, entry, "detail_chart.type", f"只可以是 {list(CHART_TYPES)}")
        series = chart.get("series")
        _need(isinstance(series, list) and series and all(_is_str(x) for x in series), entry,
              "detail_chart.series", "必填，非空的字串清單")
        if "levels" in chart:
            _need(isinstance(chart["levels"], list) and all(_is_num(x) for x in chart["levels"]), entry,
                  "detail_chart.levels", "必須是數值清單")
        if "y_range" in chart:
            yr = chart["y_range"]
            _need(isinstance(yr, list) and len(yr) == 2 and all(_is_num(x) for x in yr) and yr[0] < yr[1],
                  entry, "detail_chart.y_range", "格式是 [最小值, 最大值]")
    if "cross_section" in d:
        cs = d["cross_section"]
        _need(isinstance(cs, list), entry, "cross_section", "必須是清單")
        _need("sector" in d["scopes"], entry, "cross_section", "只適用於有 sector 範圍的指標")
        for i, op in enumerate(cs):
            where = f"cross_section[{i}]"
            _need(isinstance(op, dict), entry, where, "必須是物件")
            _need(op.get("op") in CROSS_SECTION_OPS, entry, f"{where}.op", f"只可以是 {list(CROSS_SECTION_OPS)}")
            _need(_is_str(op.get("value_key")), entry, f"{where}.value_key", "必填")
            _need(_is_str(op.get("target_key")), entry, f"{where}.target_key", "必填")
            _need(op.get("dir") in SORT_DIRS, entry, f"{where}.dir", f"只可以是 {list(SORT_DIRS)}")
    if "value_labels" in d:
        vl = d["value_labels"]
        _need(isinstance(vl, dict) and all(_is_str(v) for v in vl.values()), entry,
              "value_labels", "必須是「鍵: 文字」的物件")
        _check_text(entry, "value_labels", list(vl.values()))
    if d.get("disclaimer") is not None:
        _need(_is_str(d["disclaimer"]), entry, "disclaimer", "必須是字串或 null")

    # Rule 7: banned words in user-facing text.
    for key in ("name", "name_zh", "expert_view", "disclaimer"):
        _check_text(entry, key, d.get(key))


def _validate_sort(entry, field, sort, sector_ids):
    _need(isinstance(sort, dict), entry, field, "必須是物件")
    _need(isinstance(sort.get("indicator"), str) and sort["indicator"] in sector_ids, entry, f"{field}.indicator",
          f"「{sort.get('indicator')}」不是已啟用的板塊範圍指標")
    _need(_is_str(sort.get("value_key")), entry, f"{field}.value_key", "必填")
    _need(sort.get("dir") in SORT_DIRS, entry, f"{field}.dir", f"只可以是 {list(SORT_DIRS)}")


def validate(indicators_cfg, universe_cfg, calculators):
    """Raise RegistryError on the first rule that fails (spec B.6)."""
    validate_universe(universe_cfg)

    _need(isinstance(indicators_cfg, dict), "indicators.json", "", "頂層必須是物件")
    labels = indicators_cfg.get("ui_labels")
    _need(isinstance(labels, dict), "ui_labels", "", "必填")
    for key, text in labels.items():
        _need(_is_str(text), "ui_labels", key, "必須是非空字串")
        _check_text("ui_labels", key, text)
    for key in REQUIRED_LABELS:
        _need(key in labels, "ui_labels", key, "必填")

    inds = indicators_cfg.get("indicators")
    _need(isinstance(inds, dict) and inds, "indicators", "", "必填，至少一個指標")
    # `calculators`: {name: required params}; a plain collection of names is accepted too.
    calculators = calculators if isinstance(calculators, dict) else {name: () for name in calculators}
    for iid, d in inds.items():
        _validate_indicator(iid, d, universe_cfg, calculators)

    # Rule 5: `order` is unique inside each scope.
    for scope in SCOPES:
        seen = {}
        for iid, d in inds.items():
            block = d["scopes"].get(scope)
            if block is None:
                continue
            order = block["order"]
            _need(order not in seen, f"indicators.{iid}", f"scopes.{scope}.order",
                  f"order {order} 與「{seen.get(order)}」重複")
            seen[order] = iid

    # Rule 6: the sector table's default sort points at an enabled sector indicator.
    sector_ids = {iid for iid, _ in enabled_indicators(indicators_cfg, "sector")}
    if sector_ids:
        table = indicators_cfg.get("sector_table")
        _need(isinstance(table, dict), "sector_table", "", "有板塊範圍指標時必填")
        _validate_sort("sector_table", "default_sort", table.get("default_sort"), sector_ids)
        if table.get("tie_break") is not None:
            _validate_sort("sector_table", "tie_break", table["tie_break"], sector_ids)
