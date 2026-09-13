from .execution_normalizer import normalize_execution
from .confirmation_normalizer import normalize_confirmation
from .pnl_normalizer import normalize_pnl


def normalize_message(topic, message, instrument_mapper):
    if topic == "executions":
        return normalize_execution(message, instrument_mapper)

    if topic == "confirmations":
        return normalize_confirmation(message, instrument_mapper)

    if topic == "pnl_snapshot":
        return normalize_pnl(message, instrument_mapper)

    raise ValueError(f"Unsupported topic: {topic}")