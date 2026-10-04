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
    """{code: PositionFrame} for the wanted codes found in a raw yearly table (or several
    stacked). Codes with no rows are left out."""
    code_col = find_column(raw, CODE_COLUMN)
    date_col = find_column(raw, DATE_COLUMN)
    cols = {key: find_column(raw, name) for key, name in POSITION_COLUMNS.items()}

    table = raw[raw[code_col].astype(str).str.strip().isin(set(codes))]
    out = {}
    for code, part in table.groupby(table[code_col].astype(str).str.strip()):
        numbers = {key: pd.to_numeric(part[col].astype(str).str.replace(",", "").str.strip(), errors="coerce")
                   for key, col in cols.items()}
        frame = pd.DataFrame({
            "commercial_net": numbers["commercial_long"] - numbers["commercial_short"],
            "nonreportable_net": numbers["nonreportable_long"] - numbers["nonreportable_short"],
        })
        frame.index = pd.to_datetime(part[date_col].astype(str).str.strip(), format=DATE_FORMAT, errors="coerce")
        frame.index.name = "date"
        frame = frame[frame.index.notna()].dropna()
        frame = frame[~frame.index.duplicated(keep="last")].sort_index()
        if not frame.empty:
            out[code] = frame[COLUMNS]
    return out


def fetch_positions(codes, now=None, download=None):
    """Download the yearly files once and return a PositionStore for `codes`.
    A year that fails to download is skipped; the other years are still used."""
    codes = sorted(set(codes))
    store = PositionStore()
    if not codes:
        return store
    this_year = (now or datetime.now(timezone.utc)).year
    download = download or download_year

    tables, errors = [], []
    for year in range(this_year - YEARS_BACK, this_year + 1):
        try:
            tables.append(download(year))
        except Exception as e:  # noqa: BLE001 - one year missing must not stop the rest
            errors.append(f"{year}: {type(e).__name__}: {e}")
            print(f"[collect] CFTC {year} file failed - {type(e).__name__}: {e}")

    if not tables:
        for code in codes:
            store.fail(code, FAILED, "no CFTC yearly file could be downloaded | " + " || ".join(errors))
        return store
    try:
        frames = parse(pd.concat(tables, ignore_index=True), codes)
    except Exception as e:  # noqa: BLE001
        for code in codes:
            store.fail(code, FAILED, f"{type(e).__name__}: {e}")
        return store
    for code in codes:
        if code in frames:
            store.put(code, frames[code])
        else:
            store.fail(code, EMPTY, "contract market code not found in the downloaded files")
    return store
