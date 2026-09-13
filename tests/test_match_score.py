from app.matching.match_store import MatchStore
from app.normalization.canonical_trade import CanonicalTrade
from app.utils import parse_timestamp


def make_trade(trade_id):
    return CanonicalTrade(
        trade_id=trade_id,
        instrument_id="US0378331005",
        ticker="AAPL",
        side="BUY",
        quantity=100,
        price=190.50,
        currency="USD",
        timestamp=parse_timestamp(
            "2026-09-12T10:00:00.000"
        ),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="OMS"
    )


def test_add_execution():
    store = MatchStore()

    execution = make_trade("T001")

    store.add_execution(execution)

    assert store.execution_count() == 1
    assert execution in store.get_executions()


def test_remove_execution():
    store = MatchStore()

    execution = make_trade("T001")

    store.add_execution(execution)
    store.remove_execution(execution)

    assert store.execution_count() == 0


def test_remove_multiple_executions():
    store = MatchStore()

    trade1 = make_trade("T001")
    trade2 = make_trade("T002")

    store.add_execution(trade1)
    store.add_execution(trade2)

    store.remove_executions([
        trade1,
        trade2
    ])

    assert store.execution_count() == 0


def test_store_returns_copy():
    store = MatchStore()

    execution = make_trade("T001")

    store.add_execution(execution)

    executions = store.get_executions()

    executions.clear()

    # Clearing the returned list should not clear the real store.
    assert store.execution_count() == 1