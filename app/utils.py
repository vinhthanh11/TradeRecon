from datetime import datetime, timezone
from typing import Union, Dict, Any


def parse_timestamp(value: Union[str, datetime, Dict[str, Any]]) -> datetime:
    """
    Normalize a timestamp from:
      - ISO timestamp string
      - datetime object
      - Kafka message dictionary

    Supported dictionary fields:
      timestamp
      execution_timestamp
      broker_timestamp
      valuation_timestamp
    """

    # ---------------------------------------------------------
    # If a full Kafka message was passed in
    # ---------------------------------------------------------
    if isinstance(value, dict):

        ts_str = (
            value.get("timestamp")
            or value.get("execution_timestamp")
            or value.get("broker_timestamp")
            or value.get("valuation_timestamp")
        )

        if ts_str is None:
            raise ValueError(
                f"No timestamp field found in message. "
                f"Available fields: {list(value.keys())}"
            )

        value = ts_str

    # ---------------------------------------------------------
    # Already a datetime
    # ---------------------------------------------------------
    if isinstance(value, datetime):
        dt = value

    # ---------------------------------------------------------
    # Timestamp string
    # ---------------------------------------------------------
    elif isinstance(value, str):

        value = value.strip()

        if not value:
            raise ValueError("Timestamp is missing or empty")

        # Convert Z -> UTC offset
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(value)

        except ValueError as exc:
            raise ValueError(
                f"Invalid timestamp format: {value}"
            ) from exc

    else:
        raise TypeError(
            f"Unsupported timestamp type: {type(value).__name__}"
        )

    # ---------------------------------------------------------
    # Normalize timezone handling
    #
    # Your generated timestamps currently have no timezone:
    # 2026-09-12T10:50:16.104
    #
    # Older timestamps may have UTC:
    # 2025-07-26T10:00:00.000Z
    #
    # Python cannot subtract aware and naive datetimes.
    # So make naive timestamps UTC for reconciliation purposes.
    # ---------------------------------------------------------
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def is_within_tolerance(
    val1: float,
    val2: float,
    tolerance: float = 0.01
) -> bool:

    if val1 is None or val2 is None:
        return False

    try:
        return abs(float(val1) - float(val2)) <= tolerance

    except (TypeError, ValueError):
        return False


def is_timestamp_within_drift(
    ts1,
    ts2,
    drift_ms: int = 1000
) -> bool:
    """
    Accepts timestamp strings, datetimes,
    or full Kafka message dictionaries.
    """

    try:
        dt1 = parse_timestamp(ts1)
        dt2 = parse_timestamp(ts2)

    except (ValueError, TypeError) as exc:
        print(f"Timestamp comparison failed: {exc}")
        return False

    diff_ms = abs(
        (dt1 - dt2).total_seconds() * 1000
    )

    return diff_ms <= drift_ms


def calculate_pnl_consistency(
    expected_pnl: float,
    actual_pnl: float,
    threshold: float = 1.0
) -> bool:

    if expected_pnl is None or actual_pnl is None:
        return False

    try:
        return abs(
            float(expected_pnl) - float(actual_pnl)
        ) <= threshold

    except (TypeError, ValueError):
        return False