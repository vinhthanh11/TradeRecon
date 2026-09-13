from dataclasses import dataclass
from datetime import datetime


@dataclass
class CanonicalTrade:
    trade_id: str
    instrument_id: str
    ticker: str
    side: str
    quantity: float
    price: float
    currency: str
    timestamp: datetime
    settlement_date: str | None = None
    source: str | None = None