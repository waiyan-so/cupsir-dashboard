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
  "macro": "此為規則式研究摘要，應同時評估就業、經濟週期、流動性、信用及市場價格，不應依賴任何單一指標。",
  "market_sentiment": "已接入的 VIX、DXY、銅價及油價提供市場溫度的交叉檢查；COT、QRA、GDPNow 和 SOS 仍待後續資料管道接入。",
  "catalysts": ["查看上方未來兩周經濟日曆中的三星事件", "重要數據發布後，觀察股票、美元、長債及波動率是否同向確認"],
  "checklist": risks or pos or ["等待更多資料更新"],
  "disclaimer": "此內容僅供研究與教育用途，不構成投資建議。資料可能存在時滯、修正或供應商限制。"
}
(DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
