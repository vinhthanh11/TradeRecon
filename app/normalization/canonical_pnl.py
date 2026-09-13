from dataclasses import dataclass
from datetime import datetime
from typing import Optional
    
@dataclass
class CanonicalPnl:
    """
    Standard internal representation of a trade inside TradeRecon.

    Raw execution and broker records may have different field names,
    ticker formats, or source-specific identifiers. The normalization
    layer converts them into this common structure before reconciliation.
    """
    
    trade_id: Optional[str]
    instrument_id: Optional[str]
    ticker: Optional[str]
    realized_pnl: Optional[float]
    unrealized_pnl: Optional[float]
    fx_pnl: Optional[float]
    total_fees: Optional[float]
    net_pnl: Optional[float]
    currency: Optional[str]
    timestamp: Optional[datetime]
    source: Optional[str]
    raw_data: Optional[dict] = None