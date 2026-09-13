from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.reconcile import (
    ReconciliationEngine,
    ReconciliationResult
)

from app.normalization.canonical_trade import (
    CanonicalTrade
)

from app.utils import parse_timestamp


def make_execution(
    trade_id="T001"
):
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


def make_confirmation(
    trade_id="BRK9001"
):
    return CanonicalTrade(
        trade_id=trade_id,
        instrument_id="US0378331005",
        ticker="AAPL",
        side="BUY",
        quantity=100,
        price=190.50,
        currency="USD",
        timestamp=parse_timestamp(
            "2026-09-12T10:00:00.050"
        ),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="BROKER"
    )


def make_engine():
    db_engine = create_engine(
        "sqlite:///:memory:"
    )

    ReconciliationResult.metadata.create_all(
        db_engine
    )

    Session = sessionmaker(
        bind=db_engine
    )

    session = Session()

    recon = ReconciliationEngine(
        db_url="sqlite:///:memory:",
        db_session=session
    )

    return recon, session


def test_stale_execution_becomes_missing_confirmation():
    recon, session = make_engine()

    execution = make_execution()

    recon.process_message(
        "executions",
        execution
    )

    assert (
        recon.match_store.execution_count()
        == 1
    )

    # Zero timeout makes the test deterministic:
    # anything currently pending is stale immediately.
    recon.process_stale_records(
        timeout_seconds=0
    )

    assert (
        recon.match_store.execution_count()
        == 0
    )

    result = (
        session.query(
            ReconciliationResult
        )
        .filter_by(
            trade_id="T001"
        )
        .first()
    )

    assert result is not None

    assert (
        result.status
        == "MISMATCHED"
    )

    assert (
        result.mismatch_details[0]["reason"]
        == "MISSING_CONFIRMATION"
    )


def test_stale_confirmation_becomes_missing_execution():
    recon, session = make_engine()

    confirmation = make_confirmation()

    recon.process_message(
        "confirmations",
        confirmation
    )

    assert (
        recon.match_store.confirmation_count()
        == 1
    )

    recon.process_stale_records(
        timeout_seconds=0
    )

    assert (
        recon.match_store.confirmation_count()
        == 0
    )

    result = (
        session.query(
            ReconciliationResult
        )
        .filter_by(
            trade_id="BRK9001"
        )
        .first()
    )

    assert result is not None

    assert (
        result.status
        == "MISMATCHED"
    )

    assert (
        result.mismatch_details[0]["reason"]
        == "MISSING_EXECUTION"
    )


def test_matched_trade_does_not_age_out():
    recon, session = make_engine()

    execution = make_execution(
        "T001"
    )

    confirmation = make_confirmation(
        "BRK9001"
    )

    recon.process_message(
        "executions",
        execution
    )

    recon.process_message(
        "confirmations",
        confirmation
    )

    assert (
        recon.match_store.execution_count()
        == 0
    )

    assert (
        recon.match_store.confirmation_count()
        == 0
    )

    # Nothing should be converted into a missing-side break.
    recon.process_stale_records(
        timeout_seconds=0
    )

    results = (
        session.query(
            ReconciliationResult
        )
        .all()
    )

    assert len(results) == 1

    assert (
        results[0].status
        == "MATCHED"
    )