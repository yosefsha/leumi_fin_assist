"""A Passage returned by a Filing search, with its fused relevance score."""

from dataclasses import dataclass

from utils.passage import Passage


@dataclass(frozen=True)
class PassageHit:
    """One search result: the whole Passage and the RRF score of its best Index Entry."""

    passage: Passage
    score: float
