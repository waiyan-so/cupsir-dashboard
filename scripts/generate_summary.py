import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
dashboard = json.loads((DATA / "dashboard.json").read_text(encoding="utf-8"))
items = dashboard["indicators"]
watch = [f"{x['name_zh']}：{x['signal']}" for x in items if x["signal_color"] in ["warning", "negative", "recession"]][:5]
summary = {
  "headline": f"整體 CupSir 框架訊號：{dashboard['overall_signal']}（分數 {dashboard['total_score']}）",
  "macro": "此摘要由規則式資料管道產生。請比較宏觀、流動性及市場情緒指標，不應只依賴單一數據點。",
  "market_sentiment": "VIX、DXY、銅價與油價可用於交叉確認市場壓力或週期變化。",
  "catalysts": ["查看未來兩周的 FOMC、NFP、CPI、PCE 及 QRA 事件", "在重要數據發布後觀察市場的即時反應"],
  "checklist": watch or ["等待更多資料更新"],
  "disclaimer": "此內容僅供研究與教育用途，不構成投資建議。"
}
(DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
