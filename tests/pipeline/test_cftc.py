"""CFTC collection adapter (implementation guide 5.2): parsing, matching by contract code,
failure isolation. The sample is real data in the yearly files' own column layout."""
import pandas as pd
import pytest

from pipeline.collect import cftc, fixtures
from helpers import ROOT

REAL = ROOT / "tests" / "pipeline" / "fixtures" / "real"


@pytest.fixture(scope="module")
def sample():
    # dtype=str, exactly as download_year() reads the yearly file
    return pd.read_csv(REAL / "cftc_legacy_sample.csv", dtype=str)


def test_real_header_has_the_columns_the_parser_needs():
    header = (REAL / "cftc_legacy_header.txt").read_text(encoding="utf-8").splitlines()
    frame = pd.DataFrame(columns=header)
    assert cftc.find_column(frame, cftc.CODE_COLUMN) == "CFTC Contract Market Code"
    assert cftc.find_column(frame, cftc.DATE_COLUMN) == "As of Date in Form YYMMDD"
    for name in cftc.POSITION_COLUMNS.values():
        cftc.find_column(frame, name)


def test_crude_oil_is_one_series_across_its_rename(sample):
    names = set(sample.loc[sample["CFTC Contract Market Code"] == "067651", "Market and Exchange Names"])
    assert names == {"CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
                     "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"}
    frame = cftc.parse(sample, ["067651"])["067651"]
    assert len(frame) == 104                                     # 57 rows under the old name + 47 under the new
    assert frame.index.is_monotonic_increasing and frame.index.is_unique
    assert frame.index[0] == pd.Timestamp("2021-01-05") and frame.index[-1] == pd.Timestamp("2022-12-27")
    # no gap at the rename (2022-02-01 was the last report under the old name)
    around = frame.loc["2022-01-25":"2022-02-15"]
    assert list(around.index.strftime("%Y-%m-%d")) == ["2022-01-25", "2022-02-01", "2022-02-08", "2022-02-15"]


def test_codes_with_leading_zeros_and_letters_match(sample):
    frames = cftc.parse(sample, ["043602", "001602", "13874A"])
    assert set(frames) == {"043602", "001602", "13874A"}
    assert all(len(f) == 104 for f in frames.values())


def test_net_positions_are_long_minus_short(sample):
    frame = cftc.parse(sample, ["001602"])["001602"]
    row = frame.loc["2021-12-28"]
    assert row["commercial_net"] == 139996 - 138428
    assert row["nonreportable_net"] == 30163 - 37666
    assert list(frame.columns) == ["commercial_net", "nonreportable_net"]


def test_a_code_read_as_a_number_would_not_match(sample):
    """Why codes are read as text: as an integer 043602 becomes 43602 and no longer matches."""
    as_numbers = sample.copy()
    as_numbers["CFTC Contract Market Code"] = as_numbers["CFTC Contract Market Code"].str.lstrip("0")
    assert "043602" not in cftc.parse(as_numbers, ["043602"])


def test_unknown_code_is_left_out(sample):
    assert cftc.parse(sample, ["999999"]) == {}


def test_missing_column_is_reported_by_name(sample):
    with pytest.raises(KeyError, match="CFTC Contract Market Code"):
        cftc.parse(sample.drop(columns=["CFTC Contract Market Code"]), ["067651"])


# ---- fetch_positions: five yearly files; never a series with a hole or a stale end

NOW = pd.Timestamp("2026-10-04", tz="UTC").to_pydatetime()


def yearly(year, code="067651", weeks=52, name="WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"):
    """A made-up yearly file in the real column layout: one row per week of `year`."""
    dates = pd.date_range(f"{year}-01-06", periods=weeks, freq="7D")
    return pd.DataFrame({
        "Market and Exchange Names": name,
        "As of Date in Form YYMMDD": dates.strftime("%y%m%d"),
        "CFTC Contract Market Code": code,
        "Commercial Positions-Long (All)": [str(1000 + i) for i in range(weeks)],
        "Commercial Positions-Short (All)": "400",
        "Nonreportable Positions-Long (All)": "50",
        "Nonreportable Positions-Short (All)": "80",
    })


def test_fetch_uses_this_year_and_the_four_before(sample):
    asked = []

    def download(year):
        asked.append(year)
        return yearly(year)

    store = cftc.fetch_positions(["067651", "999999"], now=NOW, download=download)
    assert sorted(asked) == [2022, 2023, 2024, 2025, 2026]
    assert store.status == {"067651": "ok", "999999": "empty"}
    frame = store.get("067651")
    assert len(frame) == 5 * 52 and frame.index.is_monotonic_increasing and frame.index.is_unique
    assert store.get("999999") is None
    assert store.names == {"067651": "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"}


def test_a_missing_middle_year_cuts_the_series_instead_of_leaving_a_hole():
    def download(year):
        if year == 2024:
            raise ConnectionError("403")
        return yearly(year)

    frame = cftc.fetch_positions(["067651"], now=NOW, download=download).get("067651")
    assert frame.index[0].year == 2025                       # 2022 and 2023 are not used past the hole
    assert len(frame) == 2 * 52
    assert frame.index.to_series().diff().dropna().dt.days.max() <= 8     # no hole (8 days only at the made-up year end)


def test_a_yearly_file_that_cannot_be_parsed_is_treated_like_a_failed_download():
    def download(year):
        table = yearly(year)
        return table.drop(columns=["CFTC Contract Market Code"]) if year == 2025 else table

    frame = cftc.fetch_positions(["067651"], now=NOW, download=download).get("067651")
    assert len(frame) == 52 and frame.index[0].year == 2026


def test_without_the_current_year_every_code_fails_so_the_last_output_stays():
    def download(year):
        if year == 2026:
            raise FileNotFoundError("404 - not published yet")
        return yearly(year)

    store = cftc.fetch_positions(["067651", "043602"], now=NOW, download=download)
    assert store.status == {"067651": "failed", "043602": "failed"} and store.ok_count() == 0
    assert "current year" in store.errors["067651"] and "404" in store.errors["067651"]


def test_fetch_with_every_year_failing_marks_every_code_failed():
    def download(year):
        raise TimeoutError("no route")

    store = cftc.fetch_positions(["067651", "043602"], now=NOW, download=download)
    assert store.status == {"067651": "failed", "043602": "failed"} and store.ok_count() == 0
    assert "no route" in store.errors["067651"]


def test_repeated_report_date_keeps_one_row_and_is_reported(capsys):
    table = yearly(2026, weeks=4)
    table = pd.concat([table, table.iloc[[3]].assign(**{"Commercial Positions-Long (All)": "9000"})])
    frame = cftc.parse(table, ["067651"])["067651"]
    assert len(frame) == 4 and frame.index.is_unique
    assert frame["commercial_net"].iloc[-1] == 9000 - 400          # the later row wins
    assert "repeated report date" in capsys.readouterr().out


def test_unreadable_rows_are_dropped_and_reported(capsys):
    table = yearly(2026, weeks=4)
    table.loc[1, "As of Date in Form YYMMDD"] = "n/a"
    table.loc[2, "Commercial Positions-Long (All)"] = "."
    assert len(cftc.parse(table, ["067651"])["067651"]) == 2
    assert "2 row(s)" in capsys.readouterr().out


def test_codes_padded_with_spaces_in_the_file_still_match():
    table = yearly(2026, code="  067651 ", weeks=3)
    assert len(cftc.parse(table, ["067651"])["067651"]) == 3


def test_latest_names_reads_the_newest_name_per_code(sample):
    names = cftc.latest_names(sample, ["067651", "043602"])
    assert names == {"067651": "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
                     "043602": "UST 10Y NOTE - CHICAGO BOARD OF TRADE"}


def test_download_reads_the_zip_as_text_and_sends_a_browser_identity():
    import io
    import zipfile
    seen = {}

    class Response:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            pass

    def get(url, headers, timeout):
        seen.update(url=url, agent=headers["User-Agent"])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("annual.txt", '"Market and Exchange Names","CFTC Contract Market Code"\n"X","043602"\n')
        return Response(buffer.getvalue())

    raw = cftc.download_year(2026, get=get)
    assert seen["url"].endswith("deacot2026.zip") and "Mozilla" in seen["agent"]
    assert raw["CFTC Contract Market Code"].iloc[0] == "043602"       # leading zero kept


# ---- offline input

def test_load_positions_from_csv_directory(tmp_path):
    folder = tmp_path / "cftc"
    folder.mkdir()
    (folder / "043602.csv").write_text(
        "date,commercial_net,nonreportable_net\n2026-09-22,10,-3\n2026-09-15,8,-2\n", encoding="utf-8")
    store = fixtures.load_positions(tmp_path, ["043602", "067651"])
    assert store.status == {"043602": "ok", "067651": "failed"}
    frame = store.get("043602")
    assert list(frame.index.strftime("%Y-%m-%d")) == ["2026-09-15", "2026-09-22"]      # sorted oldest first
