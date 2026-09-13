from .canonical_pnl import CanonicalPnl
from ..utils import parse_timestamp


def normalize_pnl(message: dict, instrument_mapper) -> CanonicalPnl:
    instrument = instrument_mapper.resolve( isin=message.get("isin"), ticker=message.get("ticker") )

    instrument_id = ( instrument.get("isin") if instrument else message.get("isin") )

    ticker = ( instrument.get("canonical_ticker") if instrument else message.get("ticker") )

    try:
        timestamp = parse_timestamp(message)
    except (ValueError, TypeError):
        timestamp = None

    return CanonicalPnl(
        trade_id=message.get("trade_id"),
        instrument_id=instrument_id,
        ticker=ticker,
        realized_pnl=message.get("realized_pnl"),
        unrealized_pnl=message.get("unrealized_pnl"),
        fx_pnl=message.get("fx_pnl"),
        total_fees=message.get("total_fees"),
        net_pnl=message.get("net_pnl"),
        currency=message.get("pnl_currency"),
        timestamp=timestamp,
        source=message.get("source_system", "PNL_ENGINE"),
        raw_data=message
    )