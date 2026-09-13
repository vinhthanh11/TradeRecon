from app.reference.instrument_mapper import InstrumentMapper
from app.normalization.normalizer import normalize_message
from app.normalization.canonical_trade import CanonicalTrade
from app.normalization.canonical_pnl import CanonicalPnl


INSTRUMENTS_CSV = "data/instruments.csv"


def test_router_normalizes_execution():
    mapper = InstrumentMapper(INSTRUMENTS_CSV)

    message = {
        "trade_id": "T0003",
        "account_id": "ACC001",
        "side": "SELL",
        "ticker": "7203",
        "isin": "JP3633400001",
        "quantity": 200,
        "price": 2837.3387,
        "trade_currency": "JPY",
        "timestamp": "2026-09-12T10:14:42.000",
        "settlement_date": "2026-09-14",
        "source_system": "OMS"
    }

    normalized = normalize_message(
        "executions",
        message,
        mapper
    )

    assert isinstance(normalized, CanonicalTrade)
    assert normalized.trade_id == "T0003"
    assert normalized.instrument_id == "JP3633400001"
    assert normalized.ticker == "7203"
    assert normalized.source == "OMS"


def test_router_normalizes_confirmation():
    mapper = InstrumentMapper(INSTRUMENTS_CSV)

    message = {
        "trade_id": "T0003",
        "account_id": "ACC001",
        "side": "SELL",
        "ticker": "7203.T",
        "isin": "JP3633400001",
        "quantity": 200,
        "price": 2837.3387,
        "trade_currency": "JPY",
        "timestamp": "2026-09-12T10:14:42.024",
        "settlement_date": "2026-09-14",
        "source_system": "BROKER"
    }

    normalized = normalize_message(
        "confirmations",
        message,
        mapper
    )

    assert isinstance(normalized, CanonicalTrade)
    assert normalized.trade_id == "T0003"
    assert normalized.instrument_id == "JP3633400001"

    # Broker ticker 7203.T should normalize to canonical 7203.
    assert normalized.ticker == "7203"
    assert normalized.source == "BROKER"


def test_router_normalizes_pnl():
    mapper = InstrumentMapper(INSTRUMENTS_CSV)

    message = {
        "trade_id": "T0003",
        "ticker": "7203",
        "isin": "JP3633400001",
        "realized_pnl": 0.0,
        "unrealized_pnl": 61.4,
        "fx_pnl": -2.4,
        "total_fees": 0.0,
        "net_pnl": 59.0,
        "pnl_currency": "USD",
        "timestamp": "2026-09-12T16:00:00",
        "source_system": "PNL_ENGINE"
    }

    normalized = normalize_message(
        "pnl_snapshot",
        message,
        mapper
    )

    assert isinstance(normalized, CanonicalPnl)
    assert normalized.trade_id == "T0003"
    assert normalized.instrument_id == "JP3633400001"
    assert normalized.ticker == "7203"
    assert normalized.net_pnl == 59.0
    assert normalized.source == "PNL_ENGINE"


def test_router_rejects_unknown_topic():
    mapper = InstrumentMapper(INSTRUMENTS_CSV)

    message = {
        "trade_id": "T0001"
    }

    try:
        normalize_message(
            "unknown_topic",
            message,
            mapper
        )

        assert False, "Expected ValueError for unknown topic"

    except ValueError as e:
        assert "Unsupported topic" in str(e)