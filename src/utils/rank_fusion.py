"""Reciprocal Rank Fusion: merge several rankings of the same IDs into one."""

from collections.abc import Sequence

RRF_K = 60
"""The standard RRF damping constant (Cormack et al., 2009)."""


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], k: int = RRF_K
) -> list[tuple[str, float]]:
    """Fuse `rankings` (best first) into `(id, score)` pairs, best first.

    Each ID scores the sum of `1 / (k + rank)` over the rankings it appears in,
    with ranks starting at 1. Ties keep first-seen order.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
