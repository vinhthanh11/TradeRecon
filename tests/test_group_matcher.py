from app.matching.group_matcher import find_match
from app.normalization.canonical_trade import CanonicalTrade
from app.utils import parse_timestamp


def make_execution(
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


def make_confirmation(
    quantity,
    price
):
    return CanonicalTrade(
        trade_id="BRK9001",
        instrument_id="US0378331005",
        ticker="AAPL",
        side="BUY",
        quantity=quantity,
        price=price,
        currency="USD",
        timestamp=parse_timestamp(
            "2026-09-12T10:00:00.200"
        ),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="BROKER"
    )


def test_direct_one_to_one_match():
    execution = make_execution(
        "T001",
        100,
        190.20
    )

    confirmation = make_confirmation(
        100,
        190.20
    )

    result = find_match(
        [execution],
        confirmation
    )

    assert result["match_type"] == "ONE_TO_ONE"
    assert len(result["executions"]) == 1
    assert result["score"] >= 80


def test_many_to_one_match():
    execution1 = make_execution(
        "T001",
        100,
        190.10
    )

    execution2 = make_execution(
        "T002",
        100,
        190.30
    )

    confirmation = make_confirmation(
        200,
        190.20
    )

    result = find_match(
        [
            execution1,
            execution2
        ],
        confirmation
    )

    assert result["match_type"] == "MANY_TO_ONE"

    assert len(
        result["executions"]
    ) == 2

    aggregated = result[
        "aggregated_execution"
    ]

    assert aggregated.quantity == 200
    assert round(
        aggregated.price,
        2
    ) == 190.20

    assert result["score"] >= 80


def test_unmatched_trade():
    execution = make_execution(
        "T001",
        100,
        190.20
    )

    confirmation = CanonicalTrade(
        trade_id="BRK9999",
        instrument_id="DE0007164600",
        ticker="SAP",
        side="SELL",
        quantity=500,
        price=220.00,
        currency="EUR",
        timestamp=parse_timestamp(
            "2026-09-12T11:00:00.000"
        ),
        settlement_date="2026-09-15",
        account_id="ACC999",
        source="BROKER"
    )

    result = find_match(
        [execution],
        confirmation
    )

    assert result["match_type"] == "UNMATCHED"
    assert result["score"] == 0


def test_direct_match_preferred_over_aggregation():
    execution1 = make_execution(
        "T001",
        100,
        190.20
    )

    execution2 = make_execution(
        "T002",
        100,
        190.30
    )

    confirmation = make_confirmation(
        100,
        190.20
    )

    result = find_match(
        [
            execution1,
            execution2
        ],
        confirmation
    )

    assert result["match_type"] == "ONE_TO_ONE"
    assert result["executions"][0].trade_id == "T001"