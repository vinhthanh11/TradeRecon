from app.reference.instrument_mapper import InstrumentMapper
from app.normalization.execution_normalizer import normalize_execution
from app.normalization.confirmation_normalizer import normalize_confirmation


INSTRUMENTS_CSV = "data/instruments.csv"


def test_toyota_execution_and_confirmation_normalize_to_same_instrument():
    mapper = InstrumentMapper(INSTRUMENTS_CSV)

    execution = {
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

    confirmation = {
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

    normalized_execution = normalize_execution( execution, mapper )
    normalized_confirmation = normalize_confirmation( confirmation, mapper )

    assert normalized_execution.instrument_id == "JP3633400001"
    assert normalized_confirmation.instrument_id == "JP3633400001"

    assert normalized_execution.ticker == "7203"
    assert normalized_confirmation.ticker == "7203"

    assert ( normalized_execution.instrument_id == normalized_confirmation.instrument_id )


def test_normalized_trade_fields():
    mapper = InstrumentMapper(INSTRUMENTS_CSV)

    execution = {
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

    normalized = normalize_execution( execution, mapper )

    assert normalized.trade_id == "T0003"
    assert normalized.ticker == "7203"
    assert normalized.instrument_id == "JP3633400001"
    assert normalized.side == "SELL"
    assert normalized.quantity == 200
    assert normalized.price == 2837.3387
    assert normalized.currency == "JPY"
    assert normalized.account_id == "ACC001"
    assert normalized.source == "OMS"
    assert normalized.timestamp is not None