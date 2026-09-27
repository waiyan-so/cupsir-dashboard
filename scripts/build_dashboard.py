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

def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback

def fred_history(series_id, limit=90):
    if not FRED_KEY:
        raise RuntimeError("FRED_API_KEY is missing")
    r = requests.get("https://api.stlouisfed.org/fred/series/observations", params={"series_id": series_id, "api_key": FRED_KEY, "file_type": "json", "sort_order": "desc", "limit": limit}, timeout=45)
    r.raise_for_status()
    rows = [{"date": x["date"], "value": float(x["value"])} for x in r.json()["observations"] if x["value"] != "."]
    return list(reversed(rows))

def market_history(ticker, period="6mo"):
    h = yf.Ticker(ticker).history(period=period)["Close"].dropna()
    if h.empty:
        raise RuntimeError(f"No market data returned for {ticker}")
    return [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 3)} for d, v in h.items()]

def manual_indicator(iid, cfg):
    return {"value": "Manual", "data_date": "N/A", "signal": "PENDING", "signal_color": "warning", "interpretation": "Phase 2 placeholder. Add an automated or manual data-import process for this item.", "history": []}

def classify(iid, value, history):
    if iid == "sahm_rule":
        return ("RECESSION", "negative", "Sahm Rule is at or above the 0.5 recession threshold.") if value >= .5 else (("WATCH", "warning", "Sahm Rule is elevated; monitor labour-market deterioration.") if value >= .3 else (("ELEVATED", "warning", "Labour market is cooling but below the watch threshold.") if value >= .15 else ("NORMAL", "positive", "Labour market signal remains below CupSir watch thresholds.")))
    if iid == "yield_curve":
        return ("DEEP INVERSION", "negative", "Yield curve is deeply inverted.") if value < -.5 else (("INVERTED", "warning", "Yield curve remains inverted.") if value < 0 else (("RECOVERING", "warning", "Curve has normalised but requires Bear Steepening review.") if value < .3 else ("NORMAL", "positive", "Yield curve is positive.")))
    if iid == "hy_spread":
        return ("CRISIS", "negative", "High-yield spread is at crisis level.") if value > 8 else (("STRESS", "negative", "High-yield spread indicates significant credit stress.") if value > 5 else (("ELEVATED", "warning", "Credit conditions need closer attention.") if value > 3.5 else (("NORMAL", "positive", "Credit spread is in the normal range.") if value > 2.5 else ("TIGHT", "warning", "Credit spread is historically tight; monitor complacency."))))
    if iid == "on_rrp":
        return ("AMPLE", "positive", "Liquidity buffer is ample.") if value > 500 else (("MODERATE", "warning", "Liquidity buffer is moderate.") if value > 200 else (("DECLINING", "warning", "Liquidity buffer is narrowing.") if value > 50 else ("LOW", "negative", "Liquidity buffer is very low.")))
    if iid == "vix":
        return ("EXTREME FEAR", "positive", "Extreme volatility under the CupSir framework.") if value > 45 else (("FEAR", "negative", "Elevated fear; monitor whether volatility peaks and declines.") if value > 30 else (("DANGEROUS", "warning", "VIX is in the 20-30 caution zone in this framework.") if value > 20 else (("NEUTRAL", "positive", "VIX is in a normal range.") if value > 15 else ("COMPLACENT", "warning", "Low volatility can imply complacency and tail-risk sensitivity."))))
    if iid == "dxy":
        change = (history[-1]["value"] / history[-22]["value"] - 1) * 100 if len(history) >= 22 else 0
        return ("STRONG USD", "negative", f"DXY gained {change:.1f}% over roughly one month.") if change > 3 else (("USD STRENGTHENING", "warning", f"DXY gained {change:.1f}% over roughly one month.") if change > 1 else (("WEAK USD", "positive", f"DXY changed {change:.1f}% over roughly one month.") if change < -1 else ("USD NEUTRAL", "warning", f"DXY changed {change:.1f}% over roughly one month.")))
    if iid == "copper":
        low = min(x["value"] for x in history)
        rebound = (value / low - 1) * 100
        return ("BOTTOMING", "positive", f"Copper is {rebound:.1f}% above its sampled low.") if rebound > 10 else ("NEUTRAL", "warning", f"Copper is {rebound:.1f}% above its sampled low.")
    if iid == "oil":
        high = max(x["value"] for x in history)
        decline = (high - value) / high * 100
        return ("CYCLE COMPLETION", "positive", f"WTI is {decline:.1f}% below its sampled high.") if decline > 20 else (("DECLINING", "warning", f"WTI is {decline:.1f}% below its sampled high.") if decline > 10 else ("STILL HIGH", "warning", f"WTI is {decline:.1f}% below its sampled high."))
    if iid == "nfp":
        if len(history) < 2: return "UPDATED", "warning", "Latest payroll employment level loaded; month-on-month change requires a prior observation."
        delta = history[-1]["value"] - history[-2]["value"]
        return ("EMPLOYMENT RISING", "positive", f"Payroll employment changed by {delta:,.0f} thousand from the prior observation.") if delta > 0 else ("EMPLOYMENT FALLING", "warning", f"Payroll employment changed by {delta:,.0f} thousand from the prior observation.")
    if iid == "jolts":
        if len(history) < 2: return "UPDATED", "warning", "Latest job openings value loaded."
        delta = history[-1]["value"] - history[-2]["value"]
        return ("OPENINGS RISING", "positive", f"Job openings changed by {delta:,.0f} thousand from the prior observation.") if delta > 0 else ("OPENINGS FALLING", "warning", f"Job openings changed by {delta:,.0f} thousand from the prior observation.")
    return "UPDATED", "warning", "Latest source data loaded."

def get_history(iid, cfg, bls):
    if cfg["source"] == "fred": return fred_history(cfg["series_id"])
    if cfg["source"] == "market": return market_history(cfg["ticker"])
    if cfg["source"] == "bls": return bls.get("series", {}).get({"nfp":"nfp", "jolts":"jolts_openings"}.get(iid, iid), [])
    return None

def main():
    bls = read_json(DATA / "bls.json", {"series": {}})
    score_map = {"positive": 1, "warning": 0, "negative": -1}
    out = {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "overall_signal": "NEUTRAL", "total_score": 0, "indicators": []}
    for iid, cfg in INDICATORS.items():
        item = {"id": iid, "name": cfg["name"], "name_zh": cfg["name_zh"], "category": cfg["category"], "unit": cfg.get("unit", ""), "checklist": cfg["checklist"], "source_name": {"fred":"FRED", "bls":"BLS", "market":"Yahoo Finance", "calendar":"Official calendars", "manual":"Manual / Phase 3"}.get(cfg["source"], "Source"), "source_url": cfg["source_url"]}
        try:
            if cfg["source"] in {"manual", "calendar"}:
                item.update(manual_indicator(iid, cfg))
            else:
                history = get_history(iid, cfg, bls)
                if not history: raise RuntimeError("No observations returned")
                value = history[-1]["value"]
                label, color, text = classify(iid, value, history)
                item.update({"value": round(value, 3), "data_date": history[-1]["date"], "signal": label, "signal_color": color, "interpretation": text, "history": history[-60:]})
                out["total_score"] += score_map.get(color, 0)
        except Exception as exc:
            item.update({"value": "N/A", "data_date": "N/A", "signal": "UNAVAILABLE", "signal_color": "warning", "interpretation": f"Data retrieval failed: {str(exc)[:150]}", "history": []})
        out["indicators"].append(item)
    out["overall_signal"] = "BULLISH" if out["total_score"] >= 4 else ("BEARISH" if out["total_score"] <= -4 else "NEUTRAL")
    (DATA / "dashboard.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
