from dataclasses import replace
from typing import List

from app.normalization.canonical_trade import CanonicalTrade


def calculate_vwap(trades: List[CanonicalTrade]) -> float:
    """
    Calculate volume-weighted average price for a group of trades.
    """

    total_quantity = sum(
        trade.quantity or 0
        for trade in trades
    )

    if total_quantity == 0:
        return 0.0

    total_notional = sum(
        (trade.price or 0) * (trade.quantity or 0)
        for trade in trades
    )

    return total_notional / total_quantity


def validate_aggregation_group(trades: List[CanonicalTrade]) -> None:
    """
    Make sure trades can reasonably be aggregated together.

    For now, all trades must have the same:
    - instrument
    - side
    - currency
    - account
    """

    if not trades:
        raise ValueError("Cannot aggregate an empty trade list")

    first = trades[0]

    for trade in trades[1:]:
        if trade.instrument_id != first.instrument_id:
            raise ValueError(
                "Cannot aggregate trades with different instruments"
            )

        if trade.side != first.side:
            raise ValueError(
                "Cannot aggregate trades with different sides"
            )

        if trade.currency != first.currency:
            raise ValueError(
                "Cannot aggregate trades with different currencies"
            )

        if trade.account_id != first.account_id:
            raise ValueError(
                "Cannot aggregate trades with different accounts"
            )


def aggregate_trades(
    trades: List[CanonicalTrade]
) -> CanonicalTrade:
    """
    Aggregate multiple canonical fills into one synthetic canonical trade.

    The result uses:
    - summed quantity
    - VWAP price
    - earliest timestamp
    - first trade's instrument/account metadata
    """

    validate_aggregation_group(trades)

    total_quantity = sum(
        trade.quantity or 0
        for trade in trades
    )

    vwap = calculate_vwap(trades)

    timestamps = [
        trade.timestamp
        for trade in trades
        if trade.timestamp is not None
    ]

    earliest_timestamp = (
        min(timestamps)
        if timestamps
        else None
    )

    first = trades[0]

    return CanonicalTrade(
        trade_id="+".join(
            trade.trade_id
            for trade in trades
            if trade.trade_id
        ),
        instrument_id=first.instrument_id,
        ticker=first.ticker,
        side=first.side,
        quantity=total_quantity,
        price=vwap,
        currency=first.currency,
        timestamp=earliest_timestamp,
        settlement_date=first.settlement_date,
        account_id=first.account_id,
        source="AGGREGATED",
        raw_data={
            "component_trade_ids": [
                trade.trade_id
                for trade in trades
            ]
        }
    )