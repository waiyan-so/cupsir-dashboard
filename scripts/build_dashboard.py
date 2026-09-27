import json
import os
from datetime import datetime, timezone
from pathlib import Path
import requests
import yfinance as yf
from config import INDICATORS, CATEGORY_LABELS, CATEGORY_ORDER

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FRED_KEY = os.getenv("FRED_API_KEY")


def fred_observations(series_id, limit=60):
    if not FRED_KEY:
        raise RuntimeError("FRED_API_KEY is missing")
    r = requests.get("https://api.stlouisfed.org/fred/series/observations", params={
        "series_id": series_id, "api_key": FRED_KEY, "file_type": "json",
        "sort_order": "desc", "limit": limit
    }, timeout=30)
    r.raise_for_status()
    rows = []
    for item in r.json()["observations"]:
        if item["value"] != ".":
            rows.append({"date": item["date"], "value": float(item["value"])})
    return rows


def market_observations(ticker, period="3mo"):
    h = yf.Ticker(ticker).history(period=period)["Close"].dropna()
    return [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 3)} for d, v in h.items()]


def signal(indicator_id, value, history):
    if indicator_id == "sahm_rule":
        return ("RECESSION", "recession") if value >= .5 else (("WATCH", "warning") if value >= .3 else ("NORMAL", "positive"))
    if indicator_id == "yield_curve":
        return ("DEEP INVERSION", "negative") if value < -.5 else (("INVERTED", "warning") if value < 0 else (("RECOVERING", "warning") if value < .3 else ("NORMAL", "positive")))
    if indicator_id == "hy_spread":
        return ("STRESS", "negative") if value > 5 else (("ELEVATED", "warning") if value > 3.5 else (("NORMAL", "positive") if value > 2.5 else ("TIGHT", "warning")))
    if indicator_id == "gdpnow":
        return ("CONTRACTION", "negative") if value < -1 else (("NEGATIVE", "warning") if value < 0 else (("SLOW", "warning") if value < 1.5 else (("MODERATE", "positive") if value < 3 else ("STRONG", "positive"))))
    if indicator_id == "vix":
        return ("EXTREME FEAR", "positive") if value > 45 else (("FEAR", "negative") if value > 30 else (("DANGEROUS", "warning") if value > 20 else (("NEUTRAL", "positive") if value > 15 else ("COMPLACENT", "warning"))))
    if indicator_id == "dxy":
        change = ((history[-1]["value"] / history[-22]["value"] - 1) * 100) if len(history) >= 22 else 0
        return ("STRONG USD", "negative") if change > 3 else (("USD STRENGTHENING", "warning") if change > 1 else (("WEAK USD", "positive") if change < -1 else ("USD NEUTRAL", "warning")))
    if indicator_id == "copper":
        low = min(x["value"] for x in history)
        return ("BOTTOMING", "positive") if value / low - 1 > .10 else ("NEUTRAL", "warning")
    if indicator_id == "oil":
        high = max(x["value"] for x in history)
        decline = (high - value) / high * 100
        return ("CYCLE COMPLETION", "positive") if decline > 20 else (("DECLINING", "warning") if decline > 10 else ("STILL HIGH", "warning"))
    return "PENDING", "warning"


def cot_signal(cot_index, sentiment_index):
    if cot_index == "N/A" or sentiment_index == "N/A":
        return "PENDING COT IMPORT", "warning"
    if cot_index >= 80 and sentiment_index <= 20:
        return "STRONG BUY (SMART MONEY)", "positive"
    if cot_index <= 20 and sentiment_index >= 80:
        return "STRONG SELL (CROWDED LONG)", "negative"
    if cot_index >= 70:
        return "BULLISH LEAN", "positive"
    if cot_index <= 30:
        return "BEARISH LEAN", "warning"
    return "NEUTRAL", "warning"


def fetch_cot_results():
    try:
        from fetch_cot import get_cot_results
        return get_cot_results()
    except Exception as e:
        print(f"[build_dashboard] COT fetch failed, all COT indicators will show PENDING: {type(e).__name__}: {e}")
        return {}


def main():
    output = {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "overall_signal": "NEUTRAL",
              "total_score": 0, "category_labels": CATEGORY_LABELS, "category_order": CATEGORY_ORDER, "indicators": []}
    score_map = {"positive": 1, "warning": 0, "negative": -1, "recession": -2}
    cot_results = fetch_cot_results()

    for iid, cfg in INDICATORS.items():
        try:
            if cfg["source"] == "fred":
                history = list(reversed(fred_observations(cfg["series_id"])))
                value = history[-1]["value"]
                label, color = signal(iid, value, history)
                data_date = history[-1]["date"]
            elif cfg["source"] == "market":
                history = market_observations(cfg["ticker"])
                value = history[-1]["value"]
                label, color = signal(iid, value, history)
                data_date = history[-1]["date"]
            elif cfg["source"] == "cot":
                cr = cot_results.get(iid, {"value": "N/A", "sentiment": "N/A", "date": "N/A", "history": []})
                value = cr["value"]
                history = cr["history"]
                label, color = cot_signal(cr["value"], cr["sentiment"])
                data_date = cr["date"]
            else:
                raise RuntimeError(f"Unknown source for {iid}")

            output["total_score"] += score_map.get(color, 0)
            output["indicators"].append({
                "id": iid, "category": cfg["category"], "name": cfg["name"], "name_zh": cfg["name_zh"],
                "value": round(value, 3) if isinstance(value, float) else value, "unit": cfg.get("unit", ""),
                "data_date": data_date, "signal": label, "signal_color": color,
                "interpretation": f"CupSir framework classification: {label}.", "checklist": cfg["checklist"],
                "source_name": {"fred": "FRED", "market": "Yahoo Finance", "cot": "CFTC"}.get(cfg["source"], "Source"),
                "source_url": cfg["source_url"], "embed": cfg.get("embed"), "history": history[-30:]
            })
        except Exception as e:
            output["indicators"].append({
                "id": iid, "category": cfg["category"], "name": cfg["name"], "name_zh": cfg["name_zh"],
                "value": "N/A", "unit": cfg.get("unit", ""), "data_date": "N/A", "signal": "UNAVAILABLE",
                "signal_color": "warning", "interpretation": f"Data fetch failed: {str(e)[:120]}",
                "checklist": cfg["checklist"], "source_name": "Source", "source_url": cfg["source_url"],
                "embed": cfg.get("embed"), "history": []
            })

    output["overall_signal"] = "BULLISH" if output["total_score"] >= 3 else ("BEARISH" if output["total_score"] <= -3 else "NEUTRAL")
    (DATA / "dashboard.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
