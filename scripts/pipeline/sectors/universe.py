"""The sector lists: which sectors exist and which ticker plays which role.

There is one list per sector scope - the US sectors ("sector") and, optionally,
the ASX sectors ("asx_sector", spec G). Both are handled the same way.
"""

SCOPE = "sector"
SCOPES = ("sector", "asx_sector")
REQUIRED_ROLE = "subject"


def sector_subjects(universe, scope=SCOPE):
    return universe.get(scope, {}).get("subjects", [])


def validate(universe):
    """In every sector scope present: ids are unique and every sector has a subject role."""
    for scope in SCOPES:
        seen = set()
        for s in sector_subjects(universe, scope):
            if s["id"] in seen:
                raise ValueError(f"universe.{scope}.{s['id']}: id 重複")
            seen.add(s["id"])
            if REQUIRED_ROLE not in s.get("roles", {}):
                raise ValueError(f"universe.{scope}.{s['id']}: 缺少 {REQUIRED_ROLE} 角色")


def required_tickers(universe, indicators, scope=SCOPE):
    """Every ticker one sector scope needs: for each sector, the tickers of the
    roles that the given indicators use. `indicators` is [(id, definition)]."""
    roles_needed = {role for _, d in indicators for role in d["inputs"]}
    tickers = set()
    for s in sector_subjects(universe, scope):
        for role, ticker in s["roles"].items():
            if role in roles_needed:
                tickers.add(ticker)
    return tickers
