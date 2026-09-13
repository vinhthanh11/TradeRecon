from app.matching.trade_matcher import calculate_match_score, is_trade_match
from app.normalization.canonical_trade import CanonicalTrade
from app.utils import parse_timestamp


def test_same_trade_with_different_trade_ids_matches():
    execution = CanonicalTrade(
        trade_id="T0003",
        instrument_id="JP3633400001",
        ticker="7203",
        side="SELL",
        quantity=200,
        price=2837.3387,
        currency="JPY",
        timestamp=parse_timestamp("2026-09-12T10:14:42.000"),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="OMS"
    )

    confirmation = CanonicalTrade(
        trade_id="BRK9001",
        instrument_id="JP3633400001",
        ticker="7203",
        side="SELL",
        quantity=200,
        price=2837.3388,
        currency="JPY",
        timestamp=parse_timestamp("2026-09-12T10:14:42.300"),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="BROKER"
    )

    score = calculate_match_score(
        execution,
        confirmation
    )

    assert score >= 80
    assert is_trade_match(
        execution,
        confirmation
    )


def test_different_instrument_does_not_match():
    execution = CanonicalTrade(
        trade_id="T0001",
        instrument_id="US0378331005",
        ticker="AAPL",
        side="BUY",
        quantity=100,
        price=190.50,
        currency="USD",
        timestamp=parse_timestamp("2026-09-12T10:00:00.000"),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="OMS"
    )

    confirmation = CanonicalTrade(
        trade_id="BRK0001",
        instrument_id="DE0007164600",
        ticker="SAP",
        side="BUY",
        quantity=100,
        price=190.50,
        currency="USD",
        timestamp=parse_timestamp("2026-09-12T10:00:00.050"),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="BROKER"
    )

    score = calculate_match_score(
        execution,
        confirmation
    )

    assert score < 80
    assert not is_trade_match(
        execution,
        confirmation
    )


def test_price_difference_reduces_score():
    execution = CanonicalTrade(
        trade_id="T0002",
        instrument_id="US5949181045",
        ticker="MSFT",
        side="BUY",
        quantity=100,
        price=420.00,
        currency="USD",
        timestamp=parse_timestamp("2026-09-12T10:00:00.000"),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="OMS"
    )

    confirmation = CanonicalTrade(
        trade_id="BRK0002",
        instrument_id="US5949181045",
        ticker="MSFT",
        side="BUY",
        quantity=100,
        price=425.00,
        currency="USD",
        timestamp=parse_timestamp("2026-09-12T10:00:00.050"),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="BROKER"
    )

    score = calculate_match_score(
        execution,
        confirmation
    )

    assert score < 100


def test_large_timestamp_drift_reduces_score():
    execution = CanonicalTrade(
        trade_id="T0004",
        instrument_id="US0378331005",
        ticker="AAPL",
        side="SELL",
        quantity=100,
        price=190.50,
        currency="USD",
        timestamp=parse_timestamp("2026-09-12T10:00:00.000"),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="OMS"
    )

    confirmation = CanonicalTrade(
        trade_id="BRK0004",
        instrument_id="US0378331005",
        ticker="AAPL",
        side="SELL",
        quantity=100,
        price=190.50,
        currency="USD",
        timestamp=parse_timestamp("2026-09-12T10:00:05.000"),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="BROKER"
    )

    score = calculate_match_score(
        execution,
        confirmation
    )

    assert score < 100