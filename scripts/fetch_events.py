"""
Build the coming-two-weeks economic event calendar.

Design choice (kept deliberately simple, not scraped):
  - NFP dates are computed exactly (always the 1st Friday of the month).
  - FOMC dates are a hardcoded, verified list for 2026 (the Fed publishes
    these ~1-2 years ahead: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm).
  - QRA (Treasury refunding) dates are an approximation - 1st Wednesday of
    Feb/May/Aug/Nov - marked "(約)" since Treasury doesn't publish exact
    dates far in advance the way the Fed does.
  - CPI/PCE are intentionally NOT auto-computed: BLS/BEA release dates
    don't follow a clean formula and a wrong guess is worse than no entry.
    Add them to MANUAL_EVENTS below if/when you want exact dates.

Writes data/events.json: every event in the next 14 days from "today".
"""
import calendar
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Verified from https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
FOMC_DATES_2026 = [
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
    date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
]

# Add exact CPI/PCE/other dates here manually when known, e.g.:
# MANUAL_EVENTS = [{"date": date(2026, 10, 30), "title_zh": "PCE 通脹數據", "importance": 3, "notes": "..."}]
MANUAL_EVENTS = []


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """weekday: Monday=0 ... Sunday=6. n=1 -> first occurrence in the month."""
    first_day = date(year, month, 1)
    offset = (weekday - first_day.weekday()) % 7
    return first_day + timedelta(days=offset + 7 * (n - 1))


def _month_add(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def nfp_dates(window_start: date, window_end: date) -> list:
    out = []
    cur = date(window_start.year, window_start.month, 1)
    while cur <= window_end:
        d = _nth_weekday(cur.year, cur.month, 4, 1)  # 4 = Friday
        if window_start <= d <= window_end:
            out.append(d)
        cur = _month_add(cur, 1)
    return out


def qra_dates(window_start: date, window_end: date) -> list:
    out = []
    cur = date(window_start.year, window_start.month, 1)
    end_scan = window_end + timedelta(days=31)
    while cur <= end_scan:
        if cur.month in (2, 5, 8, 11):
            d = _nth_weekday(cur.year, cur.month, 2, 1)  # 2 = Wednesday
            if window_start <= d <= window_end:
                out.append(d)
        cur = _month_add(cur, 1)
    return out


def build_events(today: date = None) -> list:
    today = today or date.today()
    window_end = today + timedelta(days=14)

    events = []
    for d in nfp_dates(today, window_end):
        events.append({"date": d.isoformat(), "time": "08:30 ET", "title_zh": "非農就業報告（NFP）",
                        "notes": "關注 NFP、失業率和平均時薪。", "importance": 3})
    for d in FOMC_DATES_2026:
        if today <= d <= window_end:
            events.append({"date": d.isoformat(), "time": "14:00 ET", "title_zh": "聯儲局議息會議（FOMC）",
                            "notes": "關注利率決定、政策聲明及記者會。", "importance": 3})
    for d in qra_dates(today, window_end):
        events.append({"date": d.isoformat(), "time": "約 08:30 ET", "title_zh": "財政部季度再融資公告（QRA，約）",
                        "notes": "關注 Bills 與 Coupons 發行比例；確切日期以財政部公告為準。", "importance": 2})
    for e in MANUAL_EVENTS:
        d = e["date"]
        if today <= d <= window_end:
            events.append({**e, "date": d.isoformat()})

    events.sort(key=lambda x: x["date"])
    for e in events:
        e["stars"] = "⭐" * e.get("importance", 1)
    return events


def main():
    events = build_events()
    (DATA / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(events)} events to data/events.json")


if __name__ == "__main__":
    main()
