from . import __init__  # optional if needed
from app.utils import is_within_tolerance, is_timestamp_within_drift


def calculate_match_score(execution, confirmation):
    """
    Calculate how likely two canonical trade records
    represent the same economic trade.

    Score range: 0 to 100.
    """

    score = 0

    # Instrument identity is the strongest signal.
    if ( execution.instrument_id and confirmation.instrument_id 
        and execution.instrument_id == confirmation.instrument_id ):
        score += 40

    # BUY should normally match BUY, SELL with SELL.
    if ( execution.side and confirmation.side 
        and execution.side == confirmation.side ):
        score += 10

    # Exact quantity is a strong signal for a 1-to-1 match.
    if (execution.quantity is not None
        and confirmation.quantity is not None
        and is_within_tolerance( execution.quantity, confirmation.quantity, tolerance=0.0)):
        score += 20

    # Small price differences may come from rounding.
    if ( execution.price is not None 
        and confirmation.price is not None 
        and is_within_tolerance( execution.price, confirmation.price, tolerance=0.005 ) ): 
        score += 15

    # Execution times should be reasonably close.
    if ( execution.timestamp is not None 
        and confirmation.timestamp is not None 
        and is_timestamp_within_drift( execution.timestamp, confirmation.timestamp, drift_ms=1000 ) ):
        score += 10

    # Same account gives additional confidence.
    if ( execution.account_id 
        and confirmation.account_id 
        and execution.account_id == confirmation.account_id ):
        score += 5
        
    return score


def is_trade_match( execution, confirmation, threshold=80 ):
    """
    Return True if the pair is similar enough
    to be considered a candidate trade match.
    """

    score = calculate_match_score(
        execution,
        confirmation
    )

    return score >= threshold