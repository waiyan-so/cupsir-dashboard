"""
Sector layer (spec A.5 c).

Knows the sector list and which ticker plays which role, runs every sector
indicator for every sector through the calculation layer, and does the
comparisons between sectors (ranking). It never downloads data, never holds a
formula of its own and never writes files. It may import the calculation
layer only.
"""
from .runner import run
from .universe import required_tickers, sector_subjects, validate

__all__ = ["run", "required_tickers", "sector_subjects", "validate"]
