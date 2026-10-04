"""Economic calendar (scripts/fetch_events.py): date tables are keyed by year."""
import calendar
from datetime import date, timedelta

import fetch_events as fe


def titles(events):
    return [(e["date"], e["title_zh"]) for e in events]


# ---------------------------------------------------------------- the tables themselves

def test_every_monthly_table_has_twelve_valid_days_per_year():
    for name, cfg in fe.MONTHLY_RELEASES.items():
        assert cfg["days"], name
        for year, days in cfg["days"].items():
            assert len(days) == 12, (name, year)
            for month, day in enumerate(days, start=1):
                assert 1 <= day <= calendar.monthrange(year, month)[1], (name, year, month)


def test_nfp_table_has_twelve_valid_days_per_year():
    assert fe.NFP_DAYS
    for year, days in fe.NFP_DAYS.items():
        assert len(days) == 12, year
        for month, day in enumerate(days, start=1):
            assert 1 <= day <= calendar.monthrange(year, month)[1], (year, month)


def test_fomc_dates_sit_in_their_own_year_and_on_a_wednesday():
    for year, dates in fe.FOMC_DATES.items():
        assert len(dates) == 8, year
        assert dates == sorted(dates), year
        for d in dates:
            assert d.year == year
            assert d.weekday() == 2, d          # decision day is the Wednesday


def test_2027_fomc_dates_match_the_fed_calendar():
    assert fe.FOMC_DATES[2027] == [
        date(2027, 1, 27), date(2027, 3, 17), date(2027, 4, 28), date(2027, 6, 9),
        date(2027, 7, 28), date(2027, 9, 15), date(2027, 10, 27), date(2027, 12, 8),
    ]


# ---------------------------------------------------------------- inside a year that has tables

def test_a_window_inside_2026_needs_no_warning():
    events = fe.build_events(date(2026, 10, 5))
    assert ("2026-10-14", "消費者物價指數（CPI）") in titles(events)
    assert ("2026-10-07", "FOMC 議息紀要（Minutes）") in titles(events)
    assert fe.missing_years_warning() == ""


def test_every_event_is_inside_the_14_day_window():
    today = date(2026, 3, 1)
    for e in fe.build_events(today):
        assert today <= date.fromisoformat(e["date"]) <= today + timedelta(days=14)


# ---------------------------------------------------------------- a year without tables

def test_a_year_without_tables_is_skipped_not_borrowed_from_another_year():
    # Before the fix, 2027-01-10 printed January 2026's days as 2027 dates.
    events = fe.build_events(date(2027, 1, 10))
    monthly_titles = {cfg["title_zh"] for cfg in fe.MONTHLY_RELEASES.values()}
    assert not [e for e in events if e["title_zh"] in monthly_titles]


def test_the_missing_year_is_reported_once_with_every_table_named():
    fe.build_events(date(2027, 1, 10))
    warning = fe.missing_years_warning()
    assert "2027" in warning
    for name in fe.MONTHLY_RELEASES:
        assert name in warning
    assert warning.count("2027:") == 1


def test_a_window_that_crosses_new_year_keeps_december_and_drops_january():
    events = fe.build_events(date(2026, 12, 22))
    got = titles(events)
    assert ("2026-12-23", "核心 PCE 物價指數（個人所得與支出）") in got
    monthly_titles = {cfg["title_zh"] for cfg in fe.MONTHLY_RELEASES.values()}
    assert not [e for e in events if e["date"].startswith("2027") and e["title_zh"] in monthly_titles]
    assert "2027" in fe.missing_years_warning()


def test_the_warning_is_cleared_by_the_next_build():
    fe.build_events(date(2027, 1, 10))
    assert fe.missing_years_warning()
    fe.build_events(date(2026, 10, 5))
    assert fe.missing_years_warning() == ""


def test_fomc_meetings_of_2027_appear():
    assert ("2027-01-27", "聯儲局議息會議（FOMC）") in titles(fe.build_events(date(2027, 1, 20)))


def test_minutes_follow_the_meeting_by_21_days_across_years():
    assert ("2026-12-30", "FOMC 議息紀要（Minutes）") in titles(fe.build_events(date(2026, 12, 20)))
    assert ("2027-02-17", "FOMC 議息紀要（Minutes）") in titles(fe.build_events(date(2027, 2, 10)))


def test_a_year_with_no_fomc_table_is_reported(monkeypatch):
    monkeypatch.setattr(fe, "FOMC_DATES", {2026: fe.FOMC_DATES[2026]})
    events = fe.build_events(date(2027, 1, 20))
    assert not [e for e in events if "FOMC" in e["title_zh"]]
    assert "fomc" in fe.missing_years_warning()


def test_main_prints_one_warning_line(monkeypatch, tmp_path, capsys):
    real_build = fe.build_events
    monkeypatch.setattr(fe, "DATA", tmp_path)
    monkeypatch.setattr(fe, "build_events", lambda: real_build(date(2027, 1, 10)))
    fe.main()
    out = capsys.readouterr().out
    assert out.count("::warning::") == 1
    assert (tmp_path / "events.json").exists()


# ---------------------------------------------------------------- NFP: official dates, not "first Friday"

NFP = "非農就業報告（NFP）"


def nfp_dates_seen(today):
    return [e["date"] for e in fe.build_events(today) if e["title_zh"] == NFP]


def test_nfp_follows_the_bls_schedule_when_it_is_not_the_first_friday():
    # 3 July 2026 is the first Friday and a federal holiday; BLS releases on Thursday the 2nd.
    assert nfp_dates_seen(date(2026, 6, 25)) == ["2026-07-02"]


def test_nfp_dates_for_the_rest_of_2026():
    assert nfp_dates_seen(date(2026, 10, 1)) == ["2026-10-02"]
    assert nfp_dates_seen(date(2026, 11, 1)) == ["2026-11-06"]
    assert nfp_dates_seen(date(2026, 12, 1)) == ["2026-12-04"]


def test_nfp_is_not_invented_for_a_year_without_a_schedule():
    # Before the fix this printed "2027-01-01", New Year's Day.
    assert nfp_dates_seen(date(2026, 12, 20)) == []
    assert "nfp" in fe.missing_years_warning()
