"""The sector list: which sectors exist and which ticker plays which role."""

SCOPE = "sector"
REQUIRED_ROLE = "subject"


def sector_subjects(universe):
    return universe.get(SCOPE, {}).get("subjects", [])


def validate(universe):
    """Sector ids are unique and every sector has a subject role."""
    seen = set()
    for s in sector_subjects(universe):
        if s["id"] in seen:
            raise ValueError(f"universe.{SCOPE}.{s['id']}: id 重複")
        seen.add(s["id"])
        if REQUIRED_ROLE not in s.get("roles", {}):
            raise ValueError(f"universe.{SCOPE}.{s['id']}: 缺少 {REQUIRED_ROLE} 角色")


def required_tickers(universe, indicators):
    """Every ticker the sector scope needs: for each sector, the tickers of the
    roles that the given indicators use. `indicators` is [(id, definition)]."""
    roles_needed = {role for _, d in indicators for role in d["inputs"]}
    tickers = set()
    for s in sector_subjects(universe):
        for role, ticker in s["roles"].items():
            if role in roles_needed:
                tickers.add(ticker)
    return tickers
