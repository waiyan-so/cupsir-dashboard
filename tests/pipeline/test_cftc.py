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


# ---- fetch_positions: five yearly files, failures stay local

NOW = pd.Timestamp("2026-10-04", tz="UTC").to_pydatetime()


def test_fetch_asks_for_five_years_and_survives_one_failing(sample):
    asked = []

    def download(year):
        asked.append(year)
        if year == 2023:
            raise ConnectionError("403")
        return sample if year == 2022 else sample.iloc[0:0]

    store = cftc.fetch_positions(["067651", "999999"], now=NOW, download=download)
    assert asked == [2022, 2023, 2024, 2025, 2026]
    assert store.status == {"067651": "ok", "999999": "empty"}
    assert len(store.get("067651")) == 104 and store.get("999999") is None


def test_fetch_with_every_year_failing_marks_every_code_failed():
    def download(year):
        raise TimeoutError("no route")

    store = cftc.fetch_positions(["067651", "043602"], now=NOW, download=download)
    assert store.status == {"067651": "failed", "043602": "failed"} and store.ok_count() == 0
    assert "no route" in store.errors["067651"]


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
