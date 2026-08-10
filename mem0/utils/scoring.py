"""
Scoring utilities for hybrid retrieval.

Provides:
- **BM25 normalization**: Sigmoid normalization of raw BM25 scores to [0, 1].
- **BM25 parameter selection**: Query-length-adaptive sigmoid parameters.
- **Additive scoring**: Combined scoring with semantic + BM25 + entity boost.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional


def get_bm25_params(query: str, *, lemmatized: Optional[str] = None) -> tuple:
    """Get BM25 sigmoid parameters based on query length.

    Longer queries tend to have higher raw BM25 scores, so we adjust
    the sigmoid midpoint and steepness accordingly.

    Returns:
        (midpoint, steepness) for sigmoid normalization.
    """
    if lemmatized is None:
        from mem0.utils.lemmatization import lemmatize_for_bm25

        lemmatized = lemmatize_for_bm25(query)
    num_terms = len(lemmatized.split()) if lemmatized else 1

    if num_terms <= 3:
        return 5.0, 0.7
    elif num_terms <= 6:
        return 7.0, 0.6
    elif num_terms <= 9:
        return 9.0, 0.5
    elif num_terms <= 15:
        return 10.0, 0.5
    else:
        return 12.0, 0.5


def normalize_bm25(raw_score: float, midpoint: float, steepness: float) -> float:
    """Normalize BM25 score to [0, 1] using logistic sigmoid.

    Args:
        raw_score: Raw BM25 score (unbounded, typically 0-20+).
        midpoint: Score at which sigmoid outputs 0.5.
        steepness: Controls how quickly sigmoid transitions.

    Returns:
        Normalized score in range [0, 1].
    """
    return 1.0 / (1.0 + math.exp(-steepness * (raw_score - midpoint)))


ENTITY_BOOST_WEIGHT = 0.5


def score_and_rank(
    semantic_results: List[Dict[str, Any]],
    bm25_scores: Dict[str, float],
    entity_boosts: Dict[str, float],
    threshold: float,
    top_k: int,
    explain: bool = False,
    decay_fn: Optional[Callable[[Dict], float]] = None,
    salience_scores: Optional[Dict[str, float]] = None,
    salience_rank_weight: float = 0.0,
) -> List[Dict[str, Any]]:
    """Score candidates additively and return top-k results.

    For each candidate:
        semantic_score is taken from the result's score field.
        combined = (decayed_semantic + bm25 + entity_boost) / max_possible

    Threshold gates the original semantic_score BEFORE combining and before
    decay -- candidates below threshold are excluded regardless of decay.

    When decay_fn is provided, the semantic score is multiplied by the decay
    multiplier (from the payload) before combining. decay_fn receives the
    full payload dict and returns a multiplier in [0, 1].

    The divisor adapts based on which signals are active:
        - Semantic only: max_possible = 1.0
        - Semantic + BM25: max_possible = 2.0
        - Semantic + BM25 + entity: max_possible = 2.5
        - Semantic + entity (no BM25): max_possible = 1.5

    Args:
        semantic_results: Candidate memories from vector search.
        bm25_scores: Normalized keyword scores keyed by memory ID.
        entity_boosts: Entity-link boosts keyed by memory ID.
        threshold: Minimum semantic score required before hybrid scoring.
        top_k: Maximum number of results to return.
        explain: Include score_details in each result when true.
        salience_scores: Optional heat_s (min(access_count/100, 1)) keyed by
            memory ID. Only applied when non-empty.
        salience_rank_weight: Multiplicative weight for the salience boost;
            default 0 keeps ordering identical to current behavior.

    Returns:
        List of scored result dicts sorted by combined score descending.
    """
    has_bm25 = bool(bm25_scores)
    has_entity = bool(entity_boosts)

    max_possible = 1.0
    if has_bm25:
        max_possible += 1.0
    if has_entity:
        max_possible += ENTITY_BOOST_WEIGHT

    scored: List[Dict[str, Any]] = []

    for result in semantic_results:
        mem_id = result.get("id")
        if mem_id is None:
            continue

        semantic_score = result.get("score") or 0.0
        if semantic_score < threshold:
            continue

        mem_id_str = str(mem_id)
        bm25_score = bm25_scores.get(mem_id_str, 0.0)
        entity_boost = entity_boosts.get(mem_id_str, 0.0)

        decay_multiplier = 1.0
        if decay_fn is not None:
            decay_multiplier = decay_fn(result.get("payload", {}))
        decayed_semantic = semantic_score * decay_multiplier

        raw_combined = decayed_semantic + bm25_score + entity_boost
        combined = min(raw_combined / max_possible, 1.0)

        # Salience (usage frequency) is an opt-in multiplicative boost: final =
        # combined x (1 + weight x heat_s). Decay governs time, salience governs
        # frequency; they never stack into double decay. weight defaults to 0,
        # so ordering is byte-for-byte identical to current behavior.
        salience_active = bool(salience_scores)
        heat_s = 0.0
        salience_boost = 1.0
        if salience_active:
            heat_s = salience_scores.get(mem_id_str, 0.0)
            salience_boost = 1.0 + salience_rank_weight * heat_s
        combined = combined * salience_boost

        scored_result = {
            "id": mem_id_str,
            "score": combined,
            "payload": result.get("payload"),
        }
        if explain:
            score_details = {
                "semantic_score": semantic_score,
                "decay_multiplier": decay_multiplier,
                "decayed_semantic": decayed_semantic,
                "bm25_score": bm25_score,
                "entity_boost": entity_boost,
                "raw_score": raw_combined,
                "max_possible_score": max_possible,
                "final_score": combined,
                "threshold": threshold,
            }
            if salience_active:
                score_details.update(
                    {
                        "salience_heat": heat_s,
                        "salience_rank_weight": salience_rank_weight,
                        "salience_boost": salience_boost,
                    }
                )
            scored_result["score_details"] = score_details
        scored.append(scored_result)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
