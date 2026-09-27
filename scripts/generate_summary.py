import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
dashboard = json.loads((DATA / "dashboard.json").read_text(encoding="utf-8"))
items = dashboard.get("indicators", [])
risks = [f"{x['name_zh']}：{x['signal']}" for x in items if x.get("signal_color") in {"warning", "negative"}][:6]
pos = [f"{x['name_zh']}：{x['signal']}" for x in items if x.get("signal_color") == "positive"][:4]
summary = {
  "headline": f"整體 CupSir 框架訊號：{dashboard.get('overall_signal', 'NEUTRAL')}（分數 {dashboard.get('total_score', 0)}）",
  "macro": "此為規則式研究摘要，綜合宏觀環境（Sahm Rule、孳息曲線、信用差、GDPNow）、市場溫度（VIX、DXY、銅、油）及機構持倉（COT）三大類指標，不應依賴任何單一指標。",
  "market_sentiment": "VIX、DXY、銅價及油價提供市場溫度的交叉檢查；COT Index／Sentiment Index 反映五個市場（S&P 500、10年債、黃金、原油、美元）的機構聰明錢持倉極端程度。",
  "catalysts": ["查看上方未來兩周經濟日曆中的三星事件", "重要數據發布後，觀察股票、美元、長債及波動率是否同向確認"],
  "checklist": risks or pos or ["等待更多資料更新"],
  "disclaimer": "此內容僅供研究與教育用途，不構成投資建議。資料可能存在時滯、修正或供應商限制。"
}
(DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
