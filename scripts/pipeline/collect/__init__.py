"""
Data collection layer (spec A.5 a).

Fetches raw daily bars and hands them over in one fixed shape. This layer
knows nothing about indicators or sectors and writes no output.

PriceFrame = pandas DataFrame
  index   : trading days, oldest first, no time zone
  columns : open, high, low, close, volume
  promise : prices adjusted for splits and dividends; volume as reported;
            no rows with missing values; the last row is a finished session

PriceStore
  .get(ticker) -> PriceFrame or None      (None = could not be fetched)
  .status      : {ticker: "ok" | "failed" | "empty"}
  .errors      : {ticker: message}
"""
import pandas as pd

COLUMNS = ["open", "high", "low", "close", "volume"]

OK = "ok"
FAILED = "failed"
EMPTY = "empty"


class PriceStore:
    def __init__(self):
        self._frames = {}
        self.status = {}
        self.errors = {}

    def put(self, ticker, frame):
        self._frames[ticker] = frame
        self.status[ticker] = OK
        self.errors.pop(ticker, None)

    def fail(self, ticker, status, message):
        self._frames.pop(ticker, None)
        self.status[ticker] = status
        self.errors[ticker] = message

    def get(self, ticker):
        return self._frames.get(ticker)

    def ok_count(self):
        return sum(1 for s in self.status.values() if s == OK)


def normalize_frame(raw):
    """Bring a downloaded or loaded table into the PriceFrame shape.
    Returns an empty frame when nothing usable is left."""
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], name="date"), dtype=float)
    df = raw.rename(columns=lambda c: str(c).strip().lower())
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"columns missing: {missing}")
    df = df[COLUMNS].apply(pd.to_numeric, errors="coerce")
    index = pd.DatetimeIndex(pd.to_datetime(df.index))
    if index.tz is not None:
        index = index.tz_localize(None)
    df.index = index.normalize()
    df.index.name = "date"
    df = df.dropna()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df
