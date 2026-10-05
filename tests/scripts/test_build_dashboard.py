"""Left-hand dashboard build (scripts/build_dashboard.py)."""
import json

import pytest

import build_dashboard as bd


def boom(*args, **kwargs):
    raise RuntimeError("source is down")


def fred_rows(series_id, limit=60):
    # newest first, like the FRED API with sort_order=desc
    return [{"date": f"2026-{m:02d}-01", "value": 1.0} for m in range(9, 0, -1)]


def market_rows(ticker, period="3mo"):
    return [{"date": f"2026-09-{d:02d}", "value": 100.0 + d} for d in range(1, 29)]


def cot_rows():
    return {iid: {"value": 55.0, "sentiment": 45.0, "date": "2026-09-29",
                  "history": [{"date": "2026-09-22", "value": 50.0}, {"date": "2026-09-29", "value": 55.0}]}
            for iid, cfg in bd.INDICATORS.items() if cfg["source"] == "cot"}


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(bd, "DATA", tmp_path)
    return tmp_path


def use_sources(monkeypatch, fred=fred_rows, market=market_rows, cot=cot_rows):
    monkeypatch.setattr(bd, "fred_observations", fred)
    monkeypatch.setattr(bd, "market_observations", market)
    monkeypatch.setattr(bd, "cot_results", cot)


BASELINE_KEYS = ["updated_at", "overall_signal", "total_score", "category_labels", "category_order", "indicators"]
INDICATOR_KEYS = ["id", "category", "name", "name_zh", "value", "unit", "data_date", "signal", "signal_color",
                  "interpretation", "checklist", "source_name", "source_url", "embed", "history"]


def test_the_file_keeps_its_structure(data_dir, monkeypatch):
    use_sources(monkeypatch)
    assert bd.main() is True
    out = json.loads((data_dir / "dashboard.json").read_text(encoding="utf-8"))
    assert list(out) == BASELINE_KEYS
    assert len(out["indicators"]) == len(bd.INDICATORS)
    for item in out["indicators"]:
        assert list(item) == INDICATOR_KEYS, item["id"]


# ---------------------------------------------------------------- X8: all sources down

def test_when_every_source_fails_the_last_good_file_is_kept(data_dir, monkeypatch, capsys):
    good = '{"updated_at": "the last good run"}'
    (data_dir / "dashboard.json").write_text(good, encoding="utf-8")
    use_sources(monkeypatch, fred=boom, market=boom, cot=lambda: {})
    assert bd.main() is False
    assert (data_dir / "dashboard.json").read_text(encoding="utf-8") == good
    assert capsys.readouterr().out.count("::warning::") == 1


def test_when_every_source_fails_and_there_is_no_file_none_is_created(data_dir, monkeypatch):
    use_sources(monkeypatch, fred=boom, market=boom, cot=lambda: {})
    assert bd.main() is False
    assert not (data_dir / "dashboard.json").exists()


@pytest.mark.parametrize("working", ["fred", "market", "cot"])
def test_one_working_source_is_enough_to_write(data_dir, monkeypatch, working, capsys):
    (data_dir / "dashboard.json").write_text("{}", encoding="utf-8")
    use_sources(monkeypatch,
                fred=fred_rows if working == "fred" else boom,
                market=market_rows if working == "market" else boom,
                cot=cot_rows if working == "cot" else (lambda: {}))
    assert bd.main() is True
    out = json.loads((data_dir / "dashboard.json").read_text(encoding="utf-8"))
    with_value = [x["id"] for x in out["indicators"] if x["value"] != "N/A"]
    assert with_value and len(with_value) < len(out["indicators"])
    assert "::warning::" not in capsys.readouterr().out


# ---------------------------------------------------------------- X14: the sentence under the value

def has_cjk(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def test_interpretation_is_chinese_and_names_the_signal(data_dir, monkeypatch):
    use_sources(monkeypatch)
    bd.main()
    out = json.loads((data_dir / "dashboard.json").read_text(encoding="utf-8"))
    for item in out["indicators"]:
        assert has_cjk(item["interpretation"]), item["id"]
        assert item["signal"] in item["interpretation"], item["id"]
        assert "framework classification" not in item["interpretation"]


def test_a_failed_fetch_is_explained_in_chinese(data_dir, monkeypatch):
    use_sources(monkeypatch, fred=boom)
    bd.main()
    out = json.loads((data_dir / "dashboard.json").read_text(encoding="utf-8"))
    failed = [x for x in out["indicators"] if x["signal"] == "UNAVAILABLE"]
    assert failed
    for item in failed:
        assert has_cjk(item["interpretation"])
        assert "source is down" in item["interpretation"]
        assert "Data fetch failed" not in item["interpretation"]


def test_the_sentences_live_in_config_not_in_the_build_script():
    import inspect
    source = inspect.getsource(bd)
    assert "框架分類" not in source and "資料讀取失敗" not in source


# ---------------------------------------------------------------- X17: a quarterly series shows its quarter

QUARTERLY = {"date_as": "quarter"}


@pytest.mark.parametrize("iso, shown", [
    ("2026-01-01", "2026 年第一季"), ("2026-03-31", "2026 年第一季"),
    ("2026-04-01", "2026 年第二季"), ("2026-07-01", "2026 年第三季"),
    ("2026-10-01", "2026 年第四季"), ("2027-12-31", "2027 年第四季"),
])
def test_quarter_series_show_the_quarter(iso, shown):
    assert bd.display_date(iso, QUARTERLY) == shown


def test_other_series_keep_their_date():
    assert bd.display_date("2026-07-01", {}) == "2026-07-01"


def test_an_unreadable_date_is_passed_through():
    assert bd.display_date("N/A", QUARTERLY) == "N/A"


def test_only_gdpnow_is_marked_quarterly_and_its_history_keeps_real_dates(data_dir, monkeypatch):
    assert [iid for iid, cfg in bd.INDICATORS.items() if cfg.get("date_as") == "quarter"] == ["gdpnow"]
    use_sources(monkeypatch)
    bd.main()
    out = {x["id"]: x for x in json.loads((data_dir / "dashboard.json").read_text(encoding="utf-8"))["indicators"]}
    assert out["gdpnow"]["data_date"] == "2026 年第三季"          # fred_rows ends on 2026-09-01
    assert out["gdpnow"]["history"][-1]["date"] == "2026-09-01"
    assert out["sahm_rule"]["data_date"] == "2026-09-01"


# ---------------------------------------------------------------- D6: COT indicators come from data/cot.json

def cot_file(rows):
    return {"schema_version": 2, "updated_at": "2026-10-04 13:02 UTC", "meta": {}, "rows": rows}


def cot_row(market, cot_index=70.4, sentiment=58.4, status="ok", lookback=None, history=None):
    result = {"status": status, "reason": None if status == "ok" else "insufficient_history",
              "data_date": "2026-09-29", "state": "LONG_LEAN", "tone": "positive",
              "values": {"cot_index": cot_index, "sentiment_index": sentiment,
                         "commercial_net": 1, "nonreportable_net": 2},
              "history": history if history is not None else [
                  {"date": "2026-09-22", "cot_index": 67.8, "sentiment_index": 54.6},
                  {"date": "2026-09-29", "cot_index": cot_index, "sentiment_index": sentiment}],
              "events": []}
    return {"id": market, "name_zh": market, "group": "financial", "cftc": {},
            "results": {lookback or bd.COT_LOOKBACK: result, "another_lookback": dict(result, values={"cot_index": 1.0})}}


COT_IDS = {iid: cfg["cot_id"] for iid, cfg in bd.INDICATORS.items() if cfg["source"] == "cot"}


def write_cot(data_dir, rows):
    (data_dir / bd.COT_FILE).write_text(json.dumps(cot_file(rows)), encoding="utf-8")


def test_each_cot_indicator_takes_its_markets_one_year_row(data_dir):
    write_cot(data_dir, [cot_row(m, cot_index=10.0 + n, sentiment=90.0 - n) for n, m in enumerate(COT_IDS.values())])
    got = bd.cot_results()
    assert set(got) == set(COT_IDS)
    for n, iid in enumerate(COT_IDS):
        assert got[iid]["value"] == 10.0 + n
        assert got[iid]["sentiment"] == 90.0 - n
        assert got[iid]["date"] == "2026-09-29"
        assert got[iid]["history"][-1] == {"date": "2026-09-29", "value": 10.0 + n}


def test_the_five_indicators_name_five_different_markets_that_exist():
    universe = json.loads((bd.ROOT / "config" / "universe.json").read_text(encoding="utf-8"))
    markets = {s["id"]: s for s in universe["cot"]["subjects"]}
    assert len(COT_IDS) == 5 and len(set(COT_IDS.values())) == 5
    for market in COT_IDS.values():
        assert market in markets
    registry = json.loads((bd.ROOT / "config" / "indicators.json").read_text(encoding="utf-8"))
    assert bd.COT_LOOKBACK in registry["indicators"]


def test_oil_reads_the_nymex_contract():
    universe = json.loads((bd.ROOT / "config" / "universe.json").read_text(encoding="utf-8"))
    oil = next(s for s in universe["cot"]["subjects"] if s["id"] == COT_IDS["cot_oil"])
    assert oil["cftc_code"] == "067651"
    assert oil["cftc_name"] == "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"


def test_history_skips_points_with_no_index(data_dir):
    history = [{"date": "2026-09-15", "cot_index": None, "sentiment_index": None},
               {"date": "2026-09-22", "cot_index": 40.0, "sentiment_index": 50.0}]
    write_cot(data_dir, [cot_row(m, history=history) for m in COT_IDS.values()])
    assert bd.cot_results()["cot_sp500"]["history"] == [{"date": "2026-09-22", "value": 40.0}]


def test_a_market_missing_from_the_file_is_left_out_and_reported(data_dir, capsys):
    write_cot(data_dir, [cot_row(m) for m in COT_IDS.values() if m != COT_IDS["cot_gold"]])
    got = bd.cot_results()
    assert "cot_gold" not in got and len(got) == 4
    out = capsys.readouterr().out
    assert out.count("::warning::") == 1 and "cot_gold" in out


def test_a_result_that_is_not_ok_is_left_out(data_dir, capsys):
    rows = [cot_row(m, status="na" if m == COT_IDS["cot_10y"] else "ok") for m in COT_IDS.values()]
    write_cot(data_dir, rows)
    assert "cot_10y" not in bd.cot_results()
    assert "cot_10y" in capsys.readouterr().out


def test_no_file_means_no_cot_values_and_one_warning(data_dir, capsys):
    assert bd.cot_results() == {}
    assert capsys.readouterr().out.count("::warning::") == 1


def test_an_unreadable_file_means_no_cot_values(data_dir, capsys):
    (data_dir / bd.COT_FILE).write_text("{not json", encoding="utf-8")
    assert bd.cot_results() == {}
    assert "::warning::" in capsys.readouterr().out


def test_the_dashboard_shows_the_tabs_numbers(data_dir, monkeypatch):
    write_cot(data_dir, [cot_row(m, cot_index=85.0, sentiment=15.0) for m in COT_IDS.values()])
    monkeypatch.setattr(bd, "fred_observations", fred_rows)
    monkeypatch.setattr(bd, "market_observations", market_rows)
    bd.main()
    out = {x["id"]: x for x in json.loads((data_dir / "dashboard.json").read_text(encoding="utf-8"))["indicators"]}
    for iid in COT_IDS:
        assert out[iid]["value"] == 85.0
        assert out[iid]["signal"] == "STRONG BUY (SMART MONEY)"
        assert out[iid]["data_date"] == "2026-09-29"
        assert out[iid]["source_name"] == "CFTC"


def test_without_the_cot_file_the_other_indicators_are_still_written(data_dir, monkeypatch):
    monkeypatch.setattr(bd, "fred_observations", fred_rows)
    monkeypatch.setattr(bd, "market_observations", market_rows)
    assert bd.main() is True
    out = {x["id"]: x for x in json.loads((data_dir / "dashboard.json").read_text(encoding="utf-8"))["indicators"]}
    assert out["cot_sp500"]["value"] == "N/A" and out["cot_sp500"]["signal"] == "PENDING COT IMPORT"
    assert out["vix"]["value"] != "N/A"


def test_no_checklist_still_describes_the_old_tff_approximation():
    for cfg in bd.INDICATORS.values():
        text = " ".join(cfg["checklist"])
        assert "Dealer" not in text and "槓桿基金" not in text
