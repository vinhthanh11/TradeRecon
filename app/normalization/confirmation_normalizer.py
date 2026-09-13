from .canonical_trade import CanonicalTrade
from ..utils import parse_timestamp


def normalize_confirmation( message, instrument_mapper ):

    instrument = instrument_mapper.resolve( isin=message.get("isin"), ticker=message.get("ticker") )
    instrument_id = ( instrument.get("isin") if instrument else message.get("isin") )
    ticker = ( instrument.get("canonical_ticker") if instrument else message.get("ticker") )
    
    
    return CanonicalTrade(
        trade_id=message.get("trade_id"),
        instrument_id=instrument_id,
        ticker=ticker,
        side=message.get("side"),
        quantity=message.get("quantity"),
        price=message.get("price"),
        currency=message.get("trade_currency"),
        timestamp=parse_timestamp( message ),
        settlement_date=message.get("settlement_date"),
        account_id=message.get("account_id"), 
        source=message.get("source_system", "BROKER"),
        raw_data=message
    )
    
    
    '''
    Now, in the normalization process, we can resolve the instrument_id and ticker using the InstrumentMapper.
    For example:
    Execution: (ticker = 7203, ISIN = JP3633400001) becomes (instrument_id = JP3633400001, ticker = 7203)
    Broker: (ticker = 7203.T, ISIN = JP3633400001) also becomes (instrument_id = JP3633400001, ticker = 7203)
    
    '''
    