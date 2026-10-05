import json
from pathlib import Path

from config import INDICATORS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

ZH_DIGITS = "零一二三四五六七八九十"


def count_zh(n):
    """0-10 as a Chinese numeral, anything else as digits."""
    return ZH_DIGITS[n] if 0 <= n < len(ZH_DIGITS) else str(n)


def cot_markets(items):
    """Short names of the COT markets actually present in dashboard.json, in its order."""
    return [INDICATORS.get(x.get("id"), {}).get("summary_label") or x.get("name_zh", x.get("id", ""))
            for x in items if x.get("category") == "cot"]


def market_sentiment(items):
    text = "VIX、DXY、銅價及油價提供市場溫度的交叉檢查"
    markets = cot_markets(items)
    if markets:
        text += (f"；COT Index／Sentiment Index 反映{count_zh(len(markets))}個市場（{'、'.join(markets)}）"
                 "的機構聰明錢持倉極端程度")
    return text + "。"


def build_summary(dashboard):
    items = dashboard.get("indicators", [])
    risks = [f"{x['name_zh']}：{x['signal']}" for x in items if x.get("signal_color") in {"warning", "negative"}][:6]
    pos = [f"{x['name_zh']}：{x['signal']}" for x in items if x.get("signal_color") == "positive"][:4]
    return {
      "headline": f"整體 CupSir 框架訊號：{dashboard.get('overall_signal', 'NEUTRAL')}（分數 {dashboard.get('total_score', 0)}）",
      "macro": "此為規則式研究摘要，綜合宏觀環境（Sahm Rule、孳息曲線、信用差、GDPNow）、市場溫度（VIX、DXY、銅、油）及機構持倉（COT）三大類指標，不應依賴任何單一指標。",
      "market_sentiment": market_sentiment(items),
      "catalysts": ["查看上方未來兩周經濟日曆中的三星事件", "重要數據發布後，觀察股票、美元、長債及波動率是否同向確認"],
      "checklist": risks or pos or ["等待更多資料更新"],
      "disclaimer": "此內容僅供研究與教育用途，不構成投資建議。資料可能存在時滯、修正或供應商限制。"
    }


def main():
    dashboard = json.loads((DATA / "dashboard.json").read_text(encoding="utf-8"))
    summary = build_summary(dashboard)
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
