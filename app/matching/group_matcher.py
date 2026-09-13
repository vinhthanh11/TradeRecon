from itertools import combinations

from .trade_matcher import is_trade_match, calculate_match_score
from .aggregation import aggregate_trades


def find_direct_match(executions, confirmation, threshold=80):
    """
    Try to match one execution directly against one confirmation.
    Returns the best matching execution or None.
    """

    best_execution = None
    best_score = 0

    for execution in executions:
        score = calculate_match_score(
            execution,
            confirmation
        )

        if score > best_score:
            best_score = score
            best_execution = execution

    if best_score >= threshold:
        return {
            "match_type": "ONE_TO_ONE",
            "executions": [best_execution],
            "confirmation": confirmation,
            "score": best_score
        }

    return None


def find_aggregated_match(
    executions,
    confirmation,
    threshold=80,
    max_group_size=3
):
    """
    Try combinations of multiple executions against one confirmation.

    Example:
        Execution 1: BUY 100 @ 190.10
        Execution 2: BUY 100 @ 190.30

        Broker:
        BUY 200 @ 190.20

    The two executions are aggregated before matching.
    """

    max_group_size = min(
        max_group_size,
        len(executions)
    )

    for group_size in range(
        2,
        max_group_size + 1
    ):
        for execution_group in combinations(
            executions,
            group_size
        ):
            try:
                aggregated = aggregate_trades(
                    list(execution_group)
                )

            except ValueError:
                # These executions cannot logically be grouped together.
                continue

            score = calculate_match_score(
                aggregated,
                confirmation
            )

            if score >= threshold:
                return {
                    "match_type": "MANY_TO_ONE",
                    "executions": list(execution_group),
                    "aggregated_execution": aggregated,
                    "confirmation": confirmation,
                    "score": score
                }

    return None


def find_match(
    executions,
    confirmation,
    threshold=80,
    max_group_size=3
):
    """
    Find the best available representation match.

    Order:
    1. Try direct one-to-one matching.
    2. If no direct match exists, try many-to-one aggregation.
    """

    direct_match = find_direct_match(
        executions,
        confirmation,
        threshold
    )

    if direct_match:
        return direct_match

    aggregated_match = find_aggregated_match(
        executions,
        confirmation,
        threshold,
        max_group_size
    )

    if aggregated_match:
        return aggregated_match

    return {
        "match_type": "UNMATCHED",
        "executions": [],
        "confirmation": confirmation,
        "score": 0
    }