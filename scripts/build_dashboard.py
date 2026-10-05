import json
import os
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
import yfinance as yf
from config import (INDICATORS, CATEGORY_LABELS, CATEGORY_ORDER, INTERPRETATION_TEXT, FETCH_FAILED_TEXT,
                    QUARTER_DATE_TEXT, QUARTER_NAMES, COT_FILE, COT_LOOKBACK, MARKET_TZ, SESSION_FINAL_AFTER)

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


BAR_RULES = ("session_close", "previous_day")

# How many of the latest values each indicator's "history" holds in dashboard.json.
HISTORY_POINTS = 30


def settled_bars(rows, rule, now=None):
    """Keep only the daily bars whose value is final. rows: [{"date", "value"}], oldest first.

    The run can start at any time - the schedule slips by hours and anyone can start
    one by hand - so the newest bar Yahoo returns is often still moving:
      * a bar dated today is kept only under "session_close", and only once the US
        cash session has ended (SESSION_FINAL_AFTER, US Eastern);
      * under "previous_day" today's bar is never kept. Futures and the dollar index
        reopen an hour after they close, and their bar for the current day was seen
        to differ from the settled value on every one of five evening runs;
      * bars dated on a Saturday or Sunday, or after today, are never kept (the
        Sunday-evening session shows up as a Sunday bar and later disappears).
    "Today" is the date in MARKET_TZ at `now`. Bars dated before today were already
    final in every run checked.
    """
    if rule not in BAR_RULES:
        raise ValueError(f"unknown bar_rule {rule!r}; expected one of {BAR_RULES}")
    now_market = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(MARKET_TZ))
    today = now_market.date()
    session_over = now_market.time() >= time.fromisoformat(SESSION_FINAL_AFTER)
    keep_today = rule == "session_close" and session_over
    out = []
    for row in rows:
        day = date.fromisoformat(row["date"])
        if day.weekday() >= 5 or day > today or (day == today and not keep_today):
            continue
        out.append(row)
    return out


def market_bars(ticker, period="3mo"):
    h = yf.Ticker(ticker).history(period=period)["Close"].dropna()
    return [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 3)} for d, v in h.items()]


def market_observations(ticker, period="3mo", rule="previous_day", now=None):
    rows = settled_bars(market_bars(ticker, period), rule, now)
    if not rows:
        raise RuntimeError(f"no settled daily bar for {ticker}")
    return rows


def display_date(iso_date, cfg):
    """The data date as shown on the page. A "date_as": "quarter" series is dated by
    the first day of the quarter its value is for, so show the quarter instead of
    that day; every other date is shown as it is. History points keep real dates."""
    if cfg.get("date_as") != "quarter":
        return iso_date
    try:
        year, month = int(iso_date[:4]), int(iso_date[5:7])
        return QUARTER_DATE_TEXT.format(year=year, quarter=QUARTER_NAMES[(month - 1) // 3])
    except (ValueError, IndexError):
        return iso_date


def chart_spec(cfg):
    """dashboard.json "chart" for one indicator: always every key, so the page never guesses."""
    chart = cfg.get("chart") or {}
    return {"levels": list(chart.get("levels", [])), "y_range": chart.get("y_range"), "points": chart.get("points")}


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


NO_COT = {"value": "N/A", "sentiment": "N/A", "date": "N/A", "history": []}


def cot_results():
    """The left-hand COT indicators, read from data/cot.json.

    That file is what the COT tab shows: CFTC Legacy report, commercials for the
    COT Index and small speculators for the Sentiment Index, every point computed
    on a full lookback window. Each indicator names its market with "cot_id" and
    takes the COT_LOOKBACK result of that row, so the list and the tab cannot
    disagree. Returns {indicator id: {"value", "sentiment", "date", "history"}};
    an indicator whose market or result is missing is left out (it shows N/A) and
    named in one "::warning::" line.
    """
    wanted = {iid: cfg["cot_id"] for iid, cfg in INDICATORS.items() if cfg.get("source") == "cot"}
    try:
        rows = {row["id"]: row for row in json.loads((DATA / COT_FILE).read_text(encoding="utf-8"))["rows"]}
    except Exception as e:
        print(f"::warning::COT indicators unavailable - could not read data/{COT_FILE}: {type(e).__name__}: {e}")
        return {}

    out, missing = {}, []
    for iid, market in wanted.items():
        result = rows.get(market, {}).get("results", {}).get(COT_LOOKBACK)
        values = (result or {}).get("values") or {}
        if not result or result.get("status") != "ok" or values.get("cot_index") is None:
            missing.append(f"{iid} ({market})")
            continue
        sentiment = values.get("sentiment_index")
        out[iid] = {
            "value": float(values["cot_index"]),
            "sentiment": float(sentiment) if sentiment is not None else "N/A",
            "date": result.get("data_date") or "N/A",
            "history": [{"date": p["date"], "value": p["cot_index"]}
                        for p in result.get("history", []) if p.get("cot_index") is not None],
        }
    if missing:
        print(f"::warning::no {COT_LOOKBACK} result in data/{COT_FILE} for: {', '.join(missing)}")
    return out


def main():
    output = {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "overall_signal": "NEUTRAL",
              "total_score": 0, "category_labels": CATEGORY_LABELS, "category_order": CATEGORY_ORDER, "indicators": []}
    score_map = {"positive": 1, "warning": 0, "negative": -1, "recession": -2}
    cot = cot_results()

    for iid, cfg in INDICATORS.items():
        try:
            if cfg["source"] == "fred":
                history = list(reversed(fred_observations(cfg["series_id"])))
                value = history[-1]["value"]
                label, color = signal(iid, value, history)
                data_date = display_date(history[-1]["date"], cfg)
            elif cfg["source"] == "market":
                history = market_observations(cfg["ticker"], rule=cfg["bar_rule"])
                value = history[-1]["value"]
                label, color = signal(iid, value, history)
                data_date = history[-1]["date"]
            elif cfg["source"] == "cot":
                cr = cot.get(iid, NO_COT)
                value = cr["value"]
                history = cr["history"]
                label, color = cot_signal(cr["value"], cr["sentiment"])
                data_date = cr["date"]
            else:
                raise RuntimeError(f"Unknown source for {iid}")

            if cfg.get("scored", True):
                output["total_score"] += score_map.get(color, 0)
            output["indicators"].append({
                "id": iid, "category": cfg["category"], "name": cfg["name"], "name_zh": cfg["name_zh"],
                "value": round(value, 3) if isinstance(value, float) else value, "unit": cfg.get("unit", ""),
                "data_date": data_date, "signal": label, "signal_color": color,
                "interpretation": INTERPRETATION_TEXT.format(signal=label), "checklist": cfg["checklist"],
                "source_name": {"fred": "FRED", "market": "Yahoo Finance", "cot": "CFTC"}.get(cfg["source"], "Source"),
                "source_url": cfg["source_url"], "embed": cfg.get("embed"), "history": history[-HISTORY_POINTS:],
                "chart": chart_spec(cfg)
            })
        except Exception as e:
            output["indicators"].append({
                "id": iid, "category": cfg["category"], "name": cfg["name"], "name_zh": cfg["name_zh"],
                "value": "N/A", "unit": cfg.get("unit", ""), "data_date": "N/A", "signal": "UNAVAILABLE",
                "signal_color": "warning", "interpretation": FETCH_FAILED_TEXT.format(error=str(e)[:120]),
                "checklist": cfg["checklist"], "source_name": "Source", "source_url": cfg["source_url"],
                "embed": cfg.get("embed"), "history": [], "chart": chart_spec(cfg)
            })

    # Every source down at once (network outage, all providers failing): keep the
    # last good file rather than replace it with a page of N/A. One source failing
    # still writes - the others are fresh and the failed ones show as unavailable.
    if output["indicators"] and all(x["value"] == "N/A" for x in output["indicators"]):
        print("::warning::every dashboard indicator came back without a value (all data sources failed); "
              "data/dashboard.json was left unchanged")
        return False

    output["overall_signal"] = "BULLISH" if output["total_score"] >= 3 else ("BEARISH" if output["total_score"] <= -3 else "NEUTRAL")
    (DATA / "dashboard.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


if __name__ == "__main__":
    main()
