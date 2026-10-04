"""Rule-based research summary (scripts/generate_summary.py)."""
import json

import generate_summary as gs
from config import INDICATORS


def item(iid, category, name_zh=None, signal="NEUTRAL", color="warning"):
    return {"id": iid, "category": category, "name_zh": name_zh or iid, "signal": signal, "signal_color": color}


def cot_items(ids):
    return [item(i, "cot", INDICATORS[i]["name_zh"]) for i in ids]


ALL_COT = [iid for iid, cfg in INDICATORS.items() if cfg["source"] == "cot"]


def test_with_todays_five_markets_the_sentence_reads_as_it_always_did():
    text = gs.market_sentiment(cot_items(ALL_COT))
    assert text == ("VIX、DXY、銅價及油價提供市場溫度的交叉檢查；COT Index／Sentiment Index 反映五個市場"
                    "（S&P 500、10年債、黃金、原油、美元）的機構聰明錢持倉極端程度。")


def test_the_count_and_the_names_follow_the_data():
    text = gs.market_sentiment(cot_items(ALL_COT[:3]))
    assert "反映三個市場（S&P 500、10年債、黃金）" in text
    assert "五個市場" not in text and "原油" not in text


def test_a_market_added_to_the_data_is_counted_and_named():
    items = cot_items(ALL_COT) + [item("cot_silver", "cot", "白銀 COT")]
    text = gs.market_sentiment(items)
    assert "反映六個市場" in text and "白銀 COT" in text


def test_non_cot_indicators_are_not_counted():
    items = [item("vix", "market"), item("sahm_rule", "macro")] + cot_items(ALL_COT[:2])
    assert "反映二個市場" in gs.market_sentiment(items)


def test_with_no_cot_market_the_clause_is_left_out():
    text = gs.market_sentiment([item("vix", "market")])
    assert text == "VIX、DXY、銅價及油價提供市場溫度的交叉檢查。"


def test_more_than_ten_markets_are_counted_in_digits():
    assert gs.count_zh(10) == "十" and gs.count_zh(11) == "11"


def test_summary_keeps_its_keys(tmp_path, monkeypatch):
    dashboard = {"overall_signal": "BULLISH", "total_score": 7, "indicators": cot_items(ALL_COT)}
    (tmp_path / "dashboard.json").write_text(json.dumps(dashboard, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(gs, "DATA", tmp_path)
    gs.main()
    out = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert list(out) == ["headline", "macro", "market_sentiment", "catalysts", "checklist", "disclaimer"]
    assert out["headline"] == "整體 CupSir 框架訊號：BULLISH（分數 7）"
