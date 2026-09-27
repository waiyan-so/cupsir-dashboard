import json
import os
from datetime import datetime, timezone
from pathlib import Path
import requests
import yfinance as yf
from config import INDICATORS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FRED_KEY = os.getenv("FRED_API_KEY")

def fred_observations(series_id, limit=30):
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
    return "PENDING COT IMPORT", "warning"

def main():
    output = {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "overall_signal": "NEUTRAL", "total_score": 0, "indicators": []}
    score_map = {"positive": 1, "warning": 0, "negative": -1, "recession": -2}
    for iid, cfg in INDICATORS.items():
        try:
            if cfg["source"] == "fred":
                history = list(reversed(fred_observations(cfg["series_id"])))
            elif cfg["source"] == "market":
                history = market_observations(cfg["ticker"])
            else:
                history = [{"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "value": 50.0}]
            value = history[-1]["value"]
            label, color = signal(iid, value, history)
            output["total_score"] += score_map.get(color, 0)
            output["indicators"].append({
                "id": iid, "name": cfg["name"], "name_zh": cfg["name_zh"], "value": round(value, 3), "unit": cfg.get("unit", ""),
                "data_date": history[-1]["date"], "signal": label, "signal_color": color,
                "interpretation": f"CupSir framework classification: {label}.", "checklist": cfg["checklist"],
                "source_name": "FRED" if cfg["source"] == "fred" else ("Yahoo Finance" if cfg["source"] == "market" else "CFTC / manual import"),
                "source_url": cfg["source_url"], "history": history[-30:]
            })
        except Exception as e:
            output["indicators"].append({"id": iid, "name": cfg["name"], "name_zh": cfg["name_zh"], "value": "N/A", "unit": cfg.get("unit", ""), "data_date": "N/A", "signal": "UNAVAILABLE", "signal_color": "warning", "interpretation": f"Data fetch failed: {str(e)[:120]}", "checklist": cfg["checklist"], "source_name": "Source", "source_url": cfg["source_url"], "history": []})
    output["overall_signal"] = "BULLISH" if output["total_score"] >= 3 else ("BEARISH" if output["total_score"] <= -3 else "NEUTRAL")
    (DATA / "dashboard.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
