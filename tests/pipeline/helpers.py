"""Shared builders for hand-made price series used by the calculator tests."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def frame(closes, volumes=None, lows=None, highs=None, start="2024-01-02"):
    """A PriceFrame on consecutive business days. Open/high/low default to the close."""
    idx = pd.bdate_range(start=start, periods=len(closes))
    closes = [float(c) for c in closes]
    return pd.DataFrame({
        "open": closes,
        "high": closes if highs is None else [float(h) for h in highs],
        "low": closes if lows is None else [float(v) for v in lows],
        "close": closes,
        "volume": [1000.0] * len(closes) if volumes is None else [float(v) for v in volumes],
    }, index=idx)


def shipped_indicator(indicator_id):
    """The indicator definition exactly as shipped in config/indicators.json."""
    cfg = json.loads((ROOT / "config" / "indicators.json").read_text(encoding="utf-8"))
    return cfg["indicators"][indicator_id]


def real_fixture(name):
    """A real-price CSV from tests/pipeline/fixtures/real/ (see fixtures/request.json)."""
    path = Path(__file__).resolve().parent / "fixtures" / "real" / name
    return pd.read_csv(path, index_col="date", parse_dates=True)
