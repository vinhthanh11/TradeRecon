from app.matching.aggregation import (
    calculate_vwap,
    aggregate_trades
)

from app.normalization.canonical_trade import CanonicalTrade
from app.utils import parse_timestamp


def make_trade(
    trade_id,
    quantity,
    price
):
    return CanonicalTrade(
        trade_id=trade_id,
        instrument_id="US0378331005",
        ticker="AAPL",
        side="BUY",
        quantity=quantity,
        price=price,
        currency="USD",
        timestamp=parse_timestamp(
            "2026-09-12T10:00:00.000"
        ),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="OMS"
    )


def test_calculate_vwap():
    trade1 = make_trade(
        "T001",
        100,
        190.10
    )

    trade2 = make_trade(
        "T002",
        100,
        190.30
    )

    vwap = calculate_vwap([
        trade1,
        trade2
    ])

    assert round(vwap, 2) == 190.20


def test_aggregate_two_trades():
    trade1 = make_trade(
        "T001",
        100,
        190.10
    )

    trade2 = make_trade(
        "T002",
        100,
        190.30
    )

    aggregated = aggregate_trades([
        trade1,
        trade2
    ])

    assert aggregated.quantity == 200
    assert round(aggregated.price, 2) == 190.20

    assert (
        aggregated.instrument_id
        == "US0378331005"
    )

    assert aggregated.ticker == "AAPL"
    assert aggregated.side == "BUY"
    assert aggregated.currency == "USD"
    assert aggregated.account_id == "ACC001"
    assert aggregated.source == "AGGREGATED"


def test_aggregate_tracks_component_trade_ids():
    trade1 = make_trade(
        "T001",
        100,
        190.10
    )

    trade2 = make_trade(
        "T002",
        100,
        190.30
    )

    aggregated = aggregate_trades([
        trade1,
        trade2
    ])

    assert aggregated.raw_data[
        "component_trade_ids"
    ] == [
        "T001",
        "T002"
    ]


def test_cannot_aggregate_different_instruments():
    trade1 = make_trade(
        "T001",
        100,
        190.10
    )

    trade2 = CanonicalTrade(
        trade_id="T002",
        instrument_id="US5949181045",
        ticker="MSFT",
        side="BUY",
        quantity=100,
        price=420.00,
        currency="USD",
        timestamp=parse_timestamp(
            "2026-09-12T10:00:00.000"
        ),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="OMS"
    )

    try:
        aggregate_trades([
            trade1,
            trade2
        ])

        assert False, (
            "Expected aggregation to fail "
            "for different instruments"
        )

    except ValueError as e:
        assert (
            "different instruments"
            in str(e)
        )


def test_weighted_vwap_with_different_quantities():
    trade1 = make_trade(
        "T001",
        100,
        190.00
    )

    trade2 = make_trade(
        "T002",
        300,
        191.00
    )

    aggregated = aggregate_trades([
        trade1,
        trade2
    ])

    assert aggregated.quantity == 400

    # (100*190 + 300*191) / 400
    assert round(
        aggregated.price,
        2
    ) == 190.75