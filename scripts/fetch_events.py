"""
Build the coming-two-weeks economic event calendar.

Design choice (kept deliberately simple, not scraped):
  - NFP dates come from the BLS's own published schedule, per year, in
    NFP_DAYS. It is usually the 1st Friday of the month but not always: BLS
    moves it around holidays (2 July 2026 is a Thursday, January's is the
    second Friday), so "first Friday" is not used.
  - FOMC dates are a hardcoded, verified list per year in FOMC_DATES (the Fed
    publishes these ~1-2 years ahead:
    https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm).
  - FOMC Minutes dates are computed as meeting date + 21 days - the Fed's
    own stated rule ("minutes of regularly scheduled meetings are released
    three weeks after the policy decision"), verified against all 5 minutes
    dates already published for 2026 (Feb 18, Apr 8, May 20, Jul 8, Aug 19
    all match meeting_date + 21 days exactly).
  - QRA (Treasury refunding) dates are an approximation - 1st Wednesday of
    Feb/May/Aug/Nov - marked "(約)" since Treasury doesn't publish exact
    dates far in advance the way the Fed does.
  - MONTHLY_RELEASES below covers 11 more indicators (CPI, PPI, core
    PCE, retail sales, durable goods, housing starts, new/existing home
    sales, trade balance, ISM manufacturing/services PMI) as day-of-month
    lists per year, each one verified against that agency's own published
    release-date schedule for that year (sources in the dict's comment
    below) - NOT guessed.
  - Every date table is keyed by year. A year that has no table yet is
    skipped and reported in one "::warning::" line (shown on the Actions run
    page); dates are never carried over from another year. Yearly upkeep:
    when the agencies publish next year's schedules (usually in the last
    quarter), add that year to FOMC_DATES and to every "days" dict.
  - Still intentionally NOT auto-computed (couldn't find a clean, fully
    verified official day-by-day list for all 12 months at the time this
    was written): JOLTS, Conference Board Consumer Confidence, University
    of Michigan Consumer Sentiment, Fed Beige Book, Industrial Production
    (G.17), Empire State / Philly Fed manufacturing surveys. Add these to
    MONTHLY_RELEASES (or MANUAL_EVENTS for one-off dates) once their
    exact schedule is confirmed - a wrong guess is worse than no entry.

Writes data/events.json: every event in the next 14 days from "today".
"""
import calendar
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Decision day (second day) of each meeting, keyed by year. Verified from
# https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
# (2027 accessed 2026-10-05; the Fed marks each date tentative until it is
# confirmed at the meeting before it).
FOMC_DATES = {
    2026: [
        date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
        date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
    ],
    2027: [
        date(2027, 1, 27), date(2027, 3, 17), date(2027, 4, 28), date(2027, 6, 9),
        date(2027, 7, 28), date(2027, 9, 15), date(2027, 10, 27), date(2027, 12, 8),
    ],
}

# "days" = {year: day-of-month for Jan..Dec of that year}, verified against each
# agency's own published schedule for that year. 2026 (accessed 2026-09-28):
#   CPI/PPI/core PCE/retail sales/durable goods/new home sales/employment -
#     https://www.whitehouse.gov/wp-content/uploads/2025/09/pfei_schedule_release_dates_cy2026.pdf
#   Housing starts/trade balance -
#     https://www.census.gov/economic-indicators/econcards/assets/pdf/censusreleaseglance_2026.pdf
#   ISM manufacturing/services PMI -
#     https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/
#   Existing home sales -
#     https://www.nar.realtor/press-releases/nar-releases-2026-statistical-news-release-schedule
# 2027: no 2027 schedule could be found on these sites on 2026-10-05 (the OMB,
# BLS, Census, ISM and NAR pages still stopped at December 2026), so 2027 is
# deliberately absent. Add a 2027 list to every "days" dict once they publish.
MONTHLY_RELEASES = {
    "cpi": {
        "title_zh": "消費者物價指數（CPI）", "time": "08:30 ET", "importance": 3,
        "notes": "關注核心 CPI 按月/按年變化，市場對通脹路徑最敏感的數據之一。",
        "days": {2026: [13, 11, 11, 10, 12, 10, 14, 12, 11, 14, 10, 10]},
    },
    "ppi": {
        "title_zh": "生產者物價指數（PPI）", "time": "08:30 ET", "importance": 2,
        "notes": "上游通脹壓力指標，通常在 CPI 之後一兩日發布。",
        "days": {2026: [14, 12, 12, 14, 13, 11, 15, 13, 10, 15, 13, 15]},
    },
    "core_pce": {
        "title_zh": "核心 PCE 物價指數（個人所得與支出）", "time": "08:30 ET", "importance": 3,
        "notes": "Fed 最重視的通脹指標，直接影響利率預期。",
        "days": {2026: [29, 26, 27, 30, 28, 25, 30, 26, 30, 29, 25, 23]},
    },
    "retail_sales": {
        "title_zh": "零售銷售（Retail Sales）", "time": "08:30 ET", "importance": 2,
        "notes": "反映消費力度，對非必需消費品股份敏感度高。",
        "days": {2026: [15, 17, 16, 16, 14, 17, 16, 14, 16, 15, 17, 16]},
    },
    "durable_goods": {
        "title_zh": "耐用品訂單（Durable Goods Orders）", "time": "08:30 ET", "importance": 2,
        "notes": "企業資本開支意向的前瞻指標。",
        "days": {2026: [28, 26, 25, 24, 28, 25, 27, 26, 25, 27, 25, 23]},
    },
    "housing_starts": {
        "title_zh": "新屋開工及建築許可（Housing Starts）", "time": "08:30 ET", "importance": 2,
        "notes": "房地產週期指標，對利率敏感度高。",
        "days": {2026: [21, 18, 17, 17, 19, 16, 17, 18, 17, 20, 18, 17]},
    },
    "new_home_sales": {
        "title_zh": "新屋銷售（New Home Sales）", "time": "10:00 ET", "importance": 1,
        "notes": "房地產成交量指標。",
        "days": {2026: [27, 25, 24, 23, 27, 24, 24, 25, 24, 27, 25, 23]},
    },
    "existing_home_sales": {
        "title_zh": "成屋銷售（Existing Home Sales）", "time": "10:00 ET", "importance": 1,
        "notes": "房地產成交量指標，涵蓋範圍比新屋銷售大。",
        "days": {2026: [14, 12, 10, 13, 11, 9, 9, 11, 10, 13, 12, 9]},
    },
    "trade_balance": {
        "title_zh": "貿易帳（Trade Balance）", "time": "08:30 ET", "importance": 1,
        "notes": "進出口差額，公布數據為兩個月前的資料。",
        "days": {2026: [8, 5, 5, 2, 5, 9, 7, 4, 3, 6, 4, 8]},
    },
    "ism_manufacturing": {
        "title_zh": "ISM 製造業採購經理指數（PMI）", "time": "10:00 ET", "importance": 2,
        "notes": "50 為榮枯分界線，市場前瞻性製造業指標。",
        "days": {2026: [5, 2, 2, 1, 1, 1, 1, 3, 1, 1, 2, 1]},
    },
    "ism_services": {
        "title_zh": "ISM 服務業 PMI", "time": "10:00 ET", "importance": 2,
        "notes": "50 為榮枯分界線，服務業佔美國經濟主體。",
        "days": {2026: [7, 4, 4, 6, 5, 3, 6, 5, 3, 5, 4, 3]},
    },
}

# The Employment Situation (non-farm payrolls): {year: day-of-month for Jan..Dec}.
# 2026 from https://www.bls.gov/schedule/news_release/empsit.htm (accessed
# 2026-10-05; February is the 11th, the date BLS actually released on after
# rescheduling) - the same days as the OMB schedule above for every other month.
# 2027: not published yet on 2026-10-05, so deliberately absent.
NFP_DAYS = {
    2026: [9, 11, 6, 3, 8, 5, 2, 7, 4, 2, 6, 4],
}

# Add exact dates for anything else (JOLTS, Consumer Confidence, UMich, Beige
# Book, Industrial Production, Empire State/Philly Fed, ...) here once known:
# MANUAL_EVENTS = [{"date": date(2026, 10, 30), "title_zh": "...", "importance": 2, "notes": "..."}]
MANUAL_EVENTS = []

# (table name, year) pairs that a run needed but no table has. Filled while the
# events are built, reported once by main().
_missing_years = set()


def _years(window_start: date, window_end: date) -> list:
    return list(range(window_start.year, window_end.year + 1))


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
    return monthly_release_dates(NFP_DAYS, window_start, window_end, "nfp")


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


def fomc_dates(window_start: date, window_end: date) -> list:
    out = []
    for year in _years(window_start, window_end):
        if year not in FOMC_DATES:
            _missing_years.add(("fomc", year))
            continue
        out.extend(d for d in FOMC_DATES[year] if window_start <= d <= window_end)
    return out


def fomc_minutes_dates(window_start: date, window_end: date) -> list:
    out = []
    # A December meeting's minutes can land in the following January, so the
    # year before the window is read too (silently: only a missing year inside
    # the window is worth a warning, and fomc_dates() already records it).
    for year in [window_start.year - 1] + _years(window_start, window_end):
        for meeting_end in FOMC_DATES.get(year, []):
            d = meeting_end + timedelta(days=21)
            if window_start <= d <= window_end:
                out.append(d)
    return out


def monthly_release_dates(days_by_year: dict, window_start: date, window_end: date, name: str = "monthly") -> list:
    """days_by_year: {year: 12 ints, day-of-month for Jan..Dec of that year}.
    Months of a year that has no list are skipped and the year is recorded in
    _missing_years; another year's days are never reused."""
    out = []
    cur = date(window_start.year, window_start.month, 1)
    while cur <= window_end:
        days_by_month = days_by_year.get(cur.year)
        if days_by_month is None:
            _missing_years.add((name, cur.year))
            cur = _month_add(cur, 1)
            continue
        day = days_by_month[cur.month - 1]
        try:
            d = date(cur.year, cur.month, day)
        except ValueError:
            cur = _month_add(cur, 1)
            continue
        if window_start <= d <= window_end:
            out.append(d)
        cur = _month_add(cur, 1)
    return out


def build_events(today: date = None) -> list:
    today = today or date.today()
    window_end = today + timedelta(days=14)
    _missing_years.clear()

    events = []
    for d in nfp_dates(today, window_end):
        events.append({"date": d.isoformat(), "time": "08:30 ET", "title_zh": "非農就業報告（NFP）",
                        "notes": "關注 NFP、失業率和平均時薪。", "importance": 3})
    for d in fomc_dates(today, window_end):
        events.append({"date": d.isoformat(), "time": "14:00 ET", "title_zh": "聯儲局議息會議（FOMC）",
                        "notes": "關注利率決定、政策聲明及記者會。", "importance": 3})
    for d in fomc_minutes_dates(today, window_end):
        events.append({"date": d.isoformat(), "time": "14:00 ET", "title_zh": "FOMC 議息紀要（Minutes）",
                        "notes": "補充議息會議討論細節，關注委員分歧程度。", "importance": 2})
    for d in qra_dates(today, window_end):
        events.append({"date": d.isoformat(), "time": "約 08:30 ET", "title_zh": "財政部季度再融資公告（QRA，約）",
                        "notes": "關注 Bills 與 Coupons 發行比例；確切日期以財政部公告為準。", "importance": 2})
    for name, cfg in MONTHLY_RELEASES.items():
        for d in monthly_release_dates(cfg["days"], today, window_end, name):
            events.append({"date": d.isoformat(), "time": cfg["time"], "title_zh": cfg["title_zh"],
                            "notes": cfg["notes"], "importance": cfg["importance"]})
    for e in MANUAL_EVENTS:
        d = e["date"]
        if today <= d <= window_end:
            events.append({**e, "date": d.isoformat()})

    events.sort(key=lambda x: x["date"])
    for e in events:
        e["stars"] = "⭐" * e.get("importance", 1)
    return events


def missing_years_warning() -> str:
    """One line naming every (table, year) the last build_events() call had no
    dates for, or "" when nothing was missing."""
    if not _missing_years:
        return ""
    by_year = {}
    for name, year in sorted(_missing_years, key=lambda x: (x[1], x[0])):
        by_year.setdefault(year, []).append(name)
    parts = [f"{year}: {', '.join(names)}" for year, names in by_year.items()]
    return ("economic calendar has no release-date table for " + "; ".join(parts)
            + ". Those events are left out, not guessed. Add the year to scripts/fetch_events.py.")


def main():
    events = build_events()
    warning = missing_years_warning()
    if warning:
        print(f"::warning::{warning}")
    (DATA / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(events)} events to data/events.json")


if __name__ == "__main__":
    main()
