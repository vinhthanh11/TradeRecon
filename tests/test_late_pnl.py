from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.reconcile import ReconciliationEngine, ReconciliationResult
from app.normalization.canonical_trade import CanonicalTrade
from app.normalization.canonical_pnl import CanonicalPnl
from app.utils import parse_timestamp


def make_execution():
    return CanonicalTrade(
        trade_id="T001",
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


def make_confirmation():
    return CanonicalTrade(
        trade_id="T001",
        instrument_id="US0378331005",
        ticker="AAPL",
        side="BUY",
        quantity=100,
        price=190.50,
        currency="USD",
        timestamp=parse_timestamp("2026-09-12T10:00:00.050"),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="BROKER"
    )


def make_pnl():
    return CanonicalPnl(
        trade_id="T001",
        instrument_id="US0378331005",
        ticker="AAPL",
        realized_pnl=0.0,
        unrealized_pnl=100.0,
        fx_pnl=0.0,
        total_fees=0.50,
        net_pnl=99.50,
        currency="USD",
        timestamp=parse_timestamp("2026-09-12T16:00:00"),
        source="PNL_ENGINE"
    )


def test_late_pnl_updates_existing_reconciliation():
    # ---------------------------------------------------------
    # Create an isolated in-memory SQLite database for the test.
    # ---------------------------------------------------------
    engine = create_engine("sqlite:///:memory:")

    ReconciliationResult.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    reconciliation_engine = ReconciliationEngine(
        db_url="sqlite:///:memory:",
        db_session=session
    )

    execution = make_execution()
    confirmation = make_confirmation()
    pnl = make_pnl()

    # ---------------------------------------------------------
    # Step 1:
    # Execution arrives first and waits in MatchStore.
    # ---------------------------------------------------------
    reconciliation_engine.process_message(
        "executions",
        execution
    )

    assert (
        reconciliation_engine.match_store.execution_count()
        == 1
    )

    # ---------------------------------------------------------
    # Step 2:
    # Confirmation arrives.
    #
    # Execution + confirmation should match and create a DB row,
    # but P&L has not arrived yet.
    # ---------------------------------------------------------
    reconciliation_engine.process_message(
        "confirmations",
        confirmation
    )

    result_before_pnl = (
        session.query(ReconciliationResult)
        .filter_by(trade_id="T001")
        .first()
    )

    assert result_before_pnl is not None
    assert result_before_pnl.status == "MATCHED"
    assert result_before_pnl.pnl_data is None

    # The completed execution/confirmation pair should be
    # stored so late P&L can find it later.
    assert "T001" in reconciliation_engine.completed_matches

    # ---------------------------------------------------------
    # Step 3:
    # P&L arrives after reconciliation.
    #
    # TradeRecon should find the completed match and update
    # the existing DB row instead of creating a new one.
    # ---------------------------------------------------------
    reconciliation_engine.process_message(
        "pnl_snapshot",
        pnl
    )

    session.expire_all()

    result_after_pnl = (
        session.query(ReconciliationResult)
        .filter_by(trade_id="T001")
        .first()
    )

    assert result_after_pnl is not None
    assert result_after_pnl.status == "MATCHED"

    # P&L should now be attached to the existing record.
    assert result_after_pnl.pnl_data is not None
    assert result_after_pnl.pnl_data["trade_id"] == "T001"
    assert result_after_pnl.pnl_data["net_pnl"] == 99.50

    # P&L should no longer remain in the pending store.
    assert reconciliation_engine.match_store.pnl_count() == 0

    # ---------------------------------------------------------
    # Most important DB assertion:
    # There should still be only ONE reconciliation row.
    # ---------------------------------------------------------
    row_count = (
        session.query(ReconciliationResult)
        .filter_by(trade_id="T001")
        .count()
    )

    assert row_count == 1