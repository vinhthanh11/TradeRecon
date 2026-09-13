from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.reconcile import (
    ReconciliationEngine,
    ReconciliationResult
)

from app.normalization.canonical_trade import (
    CanonicalTrade
)

from app.normalization.canonical_pnl import (
    CanonicalPnl
)

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
        timestamp=parse_timestamp(
            "2026-09-12T10:00:00.000"
        ),
        settlement_date="2026-09-14",
        account_id="ACC001",
        source="OMS"
    )


def make_confirmation():
    return CanonicalTrade(
        trade_id="BRK9001",
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
        timestamp=parse_timestamp(
            "2026-09-12T16:00:00"
        ),
        source="PNL_ENGINE"
    )


def test_different_source_ids_map_to_same_reconciliation():
    engine = create_engine(
        "sqlite:///:memory:"
    )

    ReconciliationResult.metadata.create_all(
        engine
    )

    Session = sessionmaker(
        bind=engine
    )

    session = Session()

    recon = ReconciliationEngine(
        db_url="sqlite:///:memory:",
        db_session=session
    )

    execution = make_execution()
    confirmation = make_confirmation()

    recon.process_message(
        "executions",
        execution
    )

    recon.process_message(
        "confirmations",
        confirmation
    )

    # Different source IDs should point to
    # the same canonical reconciliation.
    assert (
        recon.reconciliation_aliases["T001"]
        == "T001"
    )

    assert (
        recon.reconciliation_aliases["BRK9001"]
        == "T001"
    )

    assert "T001" in recon.completed_matches


def test_late_pnl_uses_alias_mapping():
    engine = create_engine(
        "sqlite:///:memory:"
    )

    ReconciliationResult.metadata.create_all(
        engine
    )

    Session = sessionmaker(
        bind=engine
    )

    session = Session()

    recon = ReconciliationEngine(
        db_url="sqlite:///:memory:",
        db_session=session
    )

    execution = make_execution()
    confirmation = make_confirmation()
    pnl = make_pnl()

    recon.process_message(
        "executions",
        execution
    )

    recon.process_message(
        "confirmations",
        confirmation
    )

    recon.process_message(
        "pnl_snapshot",
        pnl
    )

    session.expire_all()

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
    assert result.pnl_data is not None

    assert (
        result.pnl_data["net_pnl"]
        == 99.50
    )

    # Broker ID should NOT create another DB row.
    assert (
        session.query(
            ReconciliationResult
        ).count()
        == 1
    )