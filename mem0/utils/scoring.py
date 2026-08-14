"""
Scoring utilities for hybrid retrieval.

Provides:
- **BM25 normalization**: Sigmoid normalization of raw BM25 scores to [0, 1].
- **BM25 parameter selection**: Query-length-adaptive sigmoid parameters.
- **Additive scoring**: Combined scoring with semantic + BM25 + entity boost.
"""

from __future__ import annotations

import math
import time
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
    salience_scores: Optional[Dict[str, Dict[str, float]]] = None,
    salience_rank_weight: float = 0.0,
    type_weight_fn: Optional[Callable[[Dict], float]] = None,
    trace_stats: Optional[Dict[str, Any]] = None,
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
        salience_scores: Optional {id: {"acc": access_count, "sal":
            salience_score}} keyed by memory ID. heat_effective =
            min(acc/100, 1) + (sal - 1); sal defaults to 1.0 so the offset is
            zero unless feedback demoted/promoted the memory. Only applied
            when non-empty.
        salience_rank_weight: Multiplicative weight for the salience boost;
            default 0 keeps ordering identical to current behavior.
        type_weight_fn: Optional per-candidate multiplicative weight applied to
            combined (after salience), receiving the full payload dict and
            returning a float. None (default) disables it entirely — a weight
            of 1.0 leaves ordering byte-for-byte identical to current behavior.
        trace_stats: Optional dict; when provided, RECALL funnel counts
            (threshold/decay/topk transitions) and latencies are written into
            it. None (default) disables all collection — zero behavior change.

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

    trace_active = trace_stats is not None
    if trace_active:
        _t0 = time.perf_counter()
        _threshold_ms = 0.0
        _decay_ms = 0.0
        _before_threshold = 0
        _after_threshold = 0
        _after_decay = 0

    for result in semantic_results:
        mem_id = result.get("id")
        if mem_id is None:
            continue

        if trace_active:
            _t_th = time.perf_counter()
            _before_threshold += 1

        semantic_score = result.get("score") or 0.0
        if semantic_score < threshold:
            if trace_active:
                _threshold_ms += time.perf_counter() - _t_th
            continue

        if trace_active:
            _threshold_ms += time.perf_counter() - _t_th
            _after_threshold += 1

        mem_id_str = str(mem_id)
        bm25_score = bm25_scores.get(mem_id_str, 0.0)
        entity_boost = entity_boosts.get(mem_id_str, 0.0)

        decay_multiplier = 1.0
        if decay_fn is not None:
            if trace_active:
                _t_dec = time.perf_counter()
            decay_multiplier = decay_fn(result.get("payload", {}))
            if trace_active:
                _decay_ms += time.perf_counter() - _t_dec
        decayed_semantic = semantic_score * decay_multiplier

        raw_combined = decayed_semantic + bm25_score + entity_boost
        combined = min(raw_combined / max_possible, 1.0)

        # Salience (usage frequency + feedback) is an opt-in multiplicative
        # boost: final = combined x (1 + weight x heat_effective), where
        # heat_effective = min(acc/100, 1) + (sal - 1). sal defaults to 1.0 so
        # a default-salience memory keeps the offset at zero; feedback demotion
        # (sal < 1) drags the memory down, promotion (sal > 1) lifts it. Decay
        # governs time, salience governs frequency; they never stack into
        # double decay. weight defaults to 0, so ordering is byte-for-byte
        # identical to current behavior.
        salience_active = bool(salience_scores)
        heat_s = 0.0
        salience_score = 1.0
        salience_boost = 1.0
        if salience_active:
            _sal = salience_scores.get(mem_id_str)
            if _sal:
                salience_score = _sal.get("sal", 1.0)
                heat_s = min(_sal.get("acc", 0) / 100.0, 1.0) + (salience_score - 1.0)
                salience_boost = 1.0 + salience_rank_weight * heat_s
            combined = combined * salience_boost

        # Memory-type weighting is an opt-in multiplicative boost on the final
        # combined score (mirrors salience). None disables it; a weight of 1.0
        # (or a payload without memory_type) leaves ordering unchanged.
        type_weight = None
        if type_weight_fn is not None:
            type_weight = type_weight_fn(result.get("payload", {}))
            combined = combined * type_weight

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
                        "salience_score": salience_score,
                        "salience_rank_weight": salience_rank_weight,
                        "salience_boost": salience_boost,
                    }
                )
            if type_weight is not None:
                score_details["type_weight"] = type_weight
            scored_result["score_details"] = score_details
        scored.append(scored_result)
        if trace_active:
            _after_decay += 1

    scored.sort(key=lambda x: x["score"], reverse=True)
    if trace_stats is not None:
        trace_stats.update(
            {
                "before_threshold": _before_threshold,
                "after_threshold": _after_threshold,
                "after_decay": _after_decay,
                "before_topk": len(scored),
                "after_topk": min(len(scored), top_k),
                "threshold_latency_ms": _threshold_ms * 1000,
                "decay_latency_ms": _decay_ms * 1000,
                "scoring_latency_ms": (time.perf_counter() - _t0) * 1000,
                "type_weights_enabled": type_weight_fn is not None,
            }
        )
    return scored[:top_k]
