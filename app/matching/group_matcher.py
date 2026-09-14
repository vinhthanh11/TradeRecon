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
        score = calculate_match_score( execution, confirmation )

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

def find_aggregated_match( executions, confirmation, threshold=80, max_group_size=3 ):
    """
    Find the strongest multiple-execution representation
    for a single broker confirmation.
    """

    max_group_size = min( max_group_size, len(executions) )

    best_match = None
    best_score = 0

    for group_size in range( 2, max_group_size + 1 ):
        for execution_group in combinations( executions, group_size ):
            try:
                aggregated = aggregate_trades( list(execution_group) )

            except ValueError:
                continue

            score = calculate_match_score( aggregated, confirmation )

            if ( score >= threshold and score > best_score ):
                best_score = score

                best_match = {
                    "match_type": "MANY_TO_ONE",
                    "executions": list( execution_group ),
                    "aggregated_execution": aggregated,
                    "confirmation": confirmation,
                    "score": score
                }

    return best_match

def find_match( executions, confirmation, threshold=80, max_group_size=3 ):
    """
    Find the best available economic representation.

    Both direct and aggregated matches are evaluated.

    The candidate with the highest score wins.

    This prevents a partial execution from being incorrectly
    accepted as ONE_TO_ONE when multiple executions together
    provide a stronger MANY_TO_ONE match.
    """

    direct_match = find_direct_match(
        executions,
        confirmation,
        threshold
    )

    aggregated_match = find_aggregated_match(
        executions,
        confirmation,
        threshold,
        max_group_size
    )

    # Neither worked.
    if not direct_match and not aggregated_match:
        return {
            "match_type": "UNMATCHED",
            "executions": [],
            "confirmation": confirmation,
            "score": 0
        }

    # Only direct worked.
    if direct_match and not aggregated_match:
        return direct_match

    # Only aggregation worked.
    if aggregated_match and not direct_match:
        return aggregated_match

    # Both are technically eligible.
    # Choose whichever explains the broker record better.
    if aggregated_match["score"] > direct_match["score"]:
        return aggregated_match

    return direct_match