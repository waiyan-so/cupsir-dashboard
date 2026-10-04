"""Weekly positions from the CFTC Legacy "Futures Only" Commitments of Traders report.

One yearly zip per year: https://www.cftc.gov/files/dea/history/deacot<year>.zip
Markets are matched by contract market code, never by name: names change
(NYMEX crude oil was renamed in February 2022, the code stayed the same).

PositionFrame = pandas DataFrame
  index   : report date (the Tuesday the positions are as of), oldest first
  columns : commercial_net, nonreportable_net     (long minus short, contracts)
  promise : no rows with missing values, one row per report date

PositionStore has the same interface as PriceStore (get / status / errors),
keyed by contract market code.
"""
import io
import zipfile
from datetime import datetime, timezone

import pandas as pd

from . import EMPTY, FAILED, PriceStore

PositionStore = PriceStore

URL = "https://www.cftc.gov/files/dea/history/deacot{year}.zip"
HEADERS = {
    # cftc.gov answers 403 to the default client identity on some networks,
    # GitHub Actions runners included; a browser-like one works.
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/zip,application/octet-stream,*/*",
}
YEARS_BACK = 4            # this year and the four before it: enough for a 3-year lookback
TIMEOUT_SECONDS = 60

COLUMNS = ["commercial_net", "nonreportable_net"]

# Column names in the yearly files. Matching ignores case, spaces and punctuation.
CODE_COLUMN = "CFTC Contract Market Code"
DATE_COLUMN = "As of Date in Form YYMMDD"
DATE_FORMAT = "%y%m%d"
NAME_COLUMN = "Market and Exchange Names"
POSITION_COLUMNS = {
    "commercial_long": "Commercial Positions-Long (All)",
    "commercial_short": "Commercial Positions-Short (All)",
    "nonreportable_long": "Nonreportable Positions-Long (All)",
    "nonreportable_short": "Nonreportable Positions-Short (All)",
}


def _key(name):
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def find_column(raw, wanted):
    """The column of `raw` whose name matches `wanted`, ignoring case and punctuation."""
    target = _key(wanted)
    for col in raw.columns:
        if _key(col) == target:
            return col
    raise KeyError(f"column '{wanted}' not found; file has {list(raw.columns)[:12]}...")


def download_year(year, get=None):
    """One yearly file as a table of strings (so codes keep their leading zeros)."""
    if get is None:
        import requests
        get = requests.get
    response = get(URL.format(year=year), headers=HEADERS, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith((".txt", ".csv"))]
        if not names:
            raise RuntimeError(f"no data file in the zip; it holds {archive.namelist()[:5]}")
        return pd.read_csv(io.BytesIO(archive.read(names[0])), dtype=str, low_memory=False)


def parse(raw, codes):
    """{code: PositionFrame} for the wanted codes found in one raw yearly table.
    Codes with no rows are left out."""
    raw = raw.reset_index(drop=True)
    code_col = find_column(raw, CODE_COLUMN)
    date_col = find_column(raw, DATE_COLUMN)
    cols = {key: find_column(raw, name) for key, name in POSITION_COLUMNS.items()}

    file_codes = raw[code_col].astype(str).str.strip()
    table = raw[file_codes.isin(set(codes))]
    out = {}
    for code, part in table.groupby(file_codes[table.index]):
        numbers = {key: pd.to_numeric(part[col].astype(str).str.replace(",", "").str.strip(), errors="coerce")
                   for key, col in cols.items()}
        frame = pd.DataFrame({
            "commercial_net": numbers["commercial_long"] - numbers["commercial_short"],
            "nonreportable_net": numbers["nonreportable_long"] - numbers["nonreportable_short"],
        })
        frame.index = pd.to_datetime(part[date_col].astype(str).str.strip(), format=DATE_FORMAT, errors="coerce")
        frame.index.name = "date"
        usable = frame[frame.index.notna()].dropna()
        if len(usable) < len(frame):
            print(f"[collect] CFTC code {code}: {len(frame) - len(usable)} row(s) with an unreadable date or number dropped")
        if not usable.empty:
            out[code] = _one_row_per_date(usable, code)[COLUMNS]
    return out


def _one_row_per_date(frame, code):
    """Sort by date; if a date appears twice keep the later row and say so."""
    repeated = int(frame.index.duplicated(keep="last").sum())
    if repeated:
        print(f"[collect] CFTC code {code}: {repeated} repeated report date(s), kept the last row of each")
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def latest_names(raw, codes):
    """{code: market name on the newest row of that code}. For checking only, never for matching."""
    raw = raw.reset_index(drop=True)
    code_col = find_column(raw, CODE_COLUMN)
    date_col = find_column(raw, DATE_COLUMN)
    name_col = find_column(raw, NAME_COLUMN)
    file_codes = raw[code_col].astype(str).str.strip()
    table = raw[file_codes.isin(set(codes))]
    newest = table.assign(_code=file_codes[table.index]).sort_values(date_col).groupby("_code").tail(1)
    return {row["_code"]: str(row[name_col]).strip() for _, row in newest.iterrows()}


def fetch_positions(codes, now=None, download=None):
    """Download the yearly files once and return a PositionStore for `codes`.

    A series must never have a hole in the middle or stop months ago and still look
    healthy, because the rolling window counts rows:
      * the current year's file is required. Without it every code is failed, so the
        last good output stays in place (this is also what happens in the first days
        of January, before the new year's file exists);
      * older years are used only as an unbroken run back from the current year. A year
        that cannot be downloaded or read cuts the series there; long lookbacks then
        come out as insufficient_history instead of spanning the hole.
    The store also carries .names: {code: market name in the newest file}.
    """
    codes = sorted(set(codes))
    store = PositionStore()
    store.names = {}
    if not codes:
        return store
    this_year = (now or datetime.now(timezone.utc)).year
    download = download or download_year

    by_year, problems = {}, []
    for year in range(this_year, this_year - YEARS_BACK - 1, -1):     # newest first
        try:
            raw = download(year)
            by_year[year] = parse(raw, codes)
            if year == this_year:
                store.names = latest_names(raw, codes)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{year}: {type(e).__name__}: {e}")
            print(f"::warning::CFTC {year} file unusable - {type(e).__name__}: {e}")
            break                                                     # nothing older is used past a hole

    if this_year not in by_year:
        for code in codes:
            store.fail(code, FAILED, "the current year's CFTC file could not be used | " + " || ".join(problems))
        return store
    for code in codes:
        parts = [by_year[year][code] for year in sorted(by_year) if code in by_year[year]]
        if parts:
            store.put(code, _one_row_per_date(pd.concat(parts), code))
        else:
            store.fail(code, EMPTY, "contract market code not found in the downloaded files")
    return store
