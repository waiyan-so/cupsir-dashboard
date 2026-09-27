import calendar
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "events.json"

# Official FOMC 2026 meeting dates. Update this list annually from the Federal Reserve calendar.
FOMC_2026 = [(1, 27, 28), (3, 17, 18), (4, 28, 29), (6, 16, 17), (7, 28, 29), (9, 15, 16), (10, 27, 28), (12, 8, 9)]

def first_weekday(year, month, weekday):
    d = date(year, month, 1)
    return d + timedelta((weekday - d.weekday()) % 7)

def nth_weekday(year, month, weekday, n):
    return first_weekday(year, month, weekday) + timedelta(days=7 * (n - 1))

def business_day_before(d):
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

def add(events, d, title, zh, importance, notes, time="TBD", url=""):
    events.append({"date": d.isoformat(), "time": time, "title": title, "title_zh": zh, "importance": importance, "notes": notes, "source_url": url})

def main():
    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=90)
    events = []
    years = range(today.year, end.year + 1)
    for year in years:
        for month in range(1, 13):
            # Employment Situation / NFP: first Friday
            add(events, first_weekday(year, month, 4), "Employment Situation", "非農就業 NFP", 3, "關注 NFP、失業率、平均時薪與市場即時反應。", "08:30 ET", "https://www.bls.gov/news.release/empsit.toc.htm")
            # CPI: approximate normal release pattern, should be checked against BLS schedule
            add(events, nth_weekday(year, month, 2, 2), "Consumer Price Index", "CPI 通脹數據", 3, "近似日期；請以 BLS 正式發布日曆覆核。", "08:30 ET", "https://www.bls.gov/schedule/news_release/cpi.htm")
            # JOLTS: approximate first business day of month
            d = date(year, month, 1)
            while d.weekday() >= 5: d += timedelta(days=1)
            add(events, d, "JOLTS", "JOLTS 職位空缺", 2, "近似日期；請以 BLS 正式發布日曆覆核。", "10:00 ET", "https://www.bls.gov/jlt/")
            # PCE: approximate final business day
            d = date(year, month, calendar.monthrange(year, month)[1])
            while d.weekday() >= 5: d -= timedelta(days=1)
            add(events, d, "Personal Income and Outlays / PCE", "PCE 通脹數據", 3, "近似日期；請以 BEA 正式發布日曆覆核。", "08:30 ET", "https://www.bea.gov/news/schedule")
            # Richmond Fed Manufacturing: fourth Tuesday
            add(events, nth_weekday(year, month, 1, 4), "Richmond Fed Manufacturing", "里奇蒙聯儲製造業", 2, "查看製造業活動是否維持擴張。", "10:00 ET", "https://www.richmondfed.org/research/regional_economy/surveys_of_business_conditions/manufacturing")
            # COT release: every Friday
            d = first_weekday(year, month, 4)
            while d.month == month:
                add(events, d, "CFTC COT Release", "COT 持倉報告", 1, "每周五公布，反映前一個周二持倉。", "15:30 ET", "https://www.cftc.gov/MarketReports/CommitmentsofTraders")
                d += timedelta(days=7)
        for m, start_day, end_day in FOMC_2026:
            if year == 2026:
                add(events, date(year, m, start_day), "FOMC Meeting", "聯儲局議息會議", 3, f"會議 {m}/{start_day}-{end_day}；關注決議、聲明和記者會。", "TBD", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
        # QRA placeholder: roughly late Jan/Apr/Jul/Oct; confirm against Treasury calendar.
        for m in [1, 4, 7, 10]:
            add(events, date(year, m, 1) + timedelta(days=27), "Quarterly Refunding Announcement", "季度再融資公告 QRA", 3, "近似日期；請以 Treasury 官方公告確認。", "TBD", "https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding")
    filtered = [e for e in events if today <= date.fromisoformat(e['date']) <= end]
    filtered.sort(key=lambda x: (x['date'], -x['importance'], x['title']))
    OUT.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
