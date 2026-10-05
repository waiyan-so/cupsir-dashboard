"""Left-hand COT indicators (scripts/fetch_cot.py): which CFTC market each one reads."""
import pandas as pd

import fetch_cot
from config import INDICATORS


def table(rows):
    """rows: (market name, date, primary_net). secondary_net is not looked at here."""
    return pd.DataFrame({
        "market": [r[0] for r in rows],
        "date": pd.to_datetime([r[1] for r in rows]),
        "primary_net": [r[2] for r in rows],
        "secondary_net": [0] * len(rows),
    })


NYMEX_OLD = "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE"
ICE = "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE"


def test_only_the_named_market_is_returned_when_several_share_a_prefix():
    df = table([
        (ICE, "2026-01-06", 1), (ICE, "2026-01-13", 2),
        (NYMEX_OLD, "2026-01-06", 100), (NYMEX_OLD, "2026-01-13", 200), (NYMEX_OLD, "2026-01-20", 300),
    ])
    got = fetch_cot._resolve_market(df, ICE)
    assert got["market"].unique().tolist() == [ICE]
    assert got["primary_net"].tolist() == [1, 2]


def test_the_market_with_more_rows_no_longer_wins():
    # The old rule kept whichever matching name had the most rows.
    df = table([(ICE, "2026-01-06", 1)] + [(NYMEX_OLD, f"2026-01-{d:02d}", d) for d in (6, 13, 20, 27)])
    assert fetch_cot._resolve_market(df, ICE)["primary_net"].tolist() == [1]


def test_equal_row_counts_give_the_same_answer_whatever_the_row_order():
    rows = [(ICE, "2026-01-06", 1), (NYMEX_OLD, "2026-01-06", 100)]
    a = fetch_cot._resolve_market(table(rows), ICE)["primary_net"].tolist()
    b = fetch_cot._resolve_market(table(rows[::-1]), ICE)["primary_net"].tolist()
    assert a == b == [1]


def test_a_longer_name_that_starts_the_same_way_is_not_matched():
    df = table([("GOLD - COMMODITY EXCHANGE INC.", "2026-01-06", 5),
                ("GOLD 100 OZ MINI - SOME EXCHANGE", "2026-01-06", 99)])
    got = fetch_cot._resolve_market(df, "GOLD - COMMODITY EXCHANGE INC.")
    assert got["primary_net"].tolist() == [5]


def test_case_and_extra_spaces_do_not_matter():
    df = table([("USD INDEX  -  ICE FUTURES U.S. ", "2026-01-06", 7)])
    assert fetch_cot._resolve_market(df, "usd index - ice futures u.s.")["primary_net"].tolist() == [7]


def test_rows_come_back_oldest_first():
    df = table([(ICE, "2026-01-13", 2), (ICE, "2026-01-06", 1)])
    assert fetch_cot._resolve_market(df, ICE)["primary_net"].tolist() == [1, 2]


def test_a_name_that_is_not_in_the_file_gives_no_rows_and_a_warning(capsys):
    df = table([(ICE, "2026-01-06", 1)])
    got = fetch_cot._resolve_market(df, "CRUDE OIL, LIGHT SWEET - NO SUCH EXCHANGE")
    assert got.empty
    out = capsys.readouterr().out
    assert out.count("::warning::") == 1
    assert ICE in out                       # the nearest real name is offered


def test_a_bare_prefix_matches_nothing(capsys):
    df = table([(ICE, "2026-01-06", 1)])
    assert fetch_cot._resolve_market(df, "CRUDE OIL, LIGHT SWEET").empty
    assert "::warning::" in capsys.readouterr().out


def test_every_cot_indicator_names_a_full_market():
    names = [cfg["cot_market"] for cfg in INDICATORS.values() if cfg.get("source") == "cot"]
    assert len(names) == 5
    for name in names:
        contract, _, exchange = name.partition(" - ")
        assert contract and exchange, name
    assert len(set(names)) == len(names)


def test_the_oil_indicator_follows_the_nymex_contract():
    assert INDICATORS["cot_oil"]["cot_market"] == "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"
