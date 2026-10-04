"""pytest setup: make scripts/ importable the same way `python scripts/xxx.py` does.

The repo root has a config/ folder and scripts/ has a config.py module, so the
new code never does `import config`; it reads config/*.json by file path.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


# ---------------------------------------------------------------- offline price set

import json  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

OFFLINE_ROWS = 520
OFFLINE_END = "2026-10-02"


def all_tickers():
    """Every ticker named in config/universe.json (tests never spell tickers out)."""
    universe = json.loads((ROOT / "config" / "universe.json").read_text(encoding="utf-8"))
    tickers = []
    for scope in ("market", "sector"):
        for s in universe[scope]["subjects"]:
            tickers.extend(s["roles"].values())
    return sorted(set(tickers))


def write_offline_prices(directory, tickers, rows=OFFLINE_ROWS, seed=7):
    """Deterministic made-up daily bars, one CSV per ticker, in DIR/prices/."""
    folder = Path(directory) / "prices"
    folder.mkdir(parents=True, exist_ok=True)
    index = pd.bdate_range(end=OFFLINE_END, periods=rows)
    for n, ticker in enumerate(tickers):
        rng = np.random.default_rng(seed + n)
        close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.011, rows)))
        frame = pd.DataFrame({
            "open": close * (1 + rng.normal(0, 0.002, rows)),
            "high": close * (1 + np.abs(rng.normal(0, 0.006, rows))),
            "low": close * (1 - np.abs(rng.normal(0, 0.006, rows))),
            "close": close,
            "volume": rng.integers(1_000_000, 9_000_000, rows).astype(float),
        }, index=index)
        frame.index.name = "date"
        frame.to_csv(folder / f"{ticker}.csv", float_format="%.6f")
    return Path(directory)


@pytest.fixture
def offline_dir(tmp_path):
    return write_offline_prices(tmp_path / "offline", all_tickers())
