"""A cross-reference resolved to the Filing's Passages."""

from dataclasses import dataclass

from utils.passage import Passage


@dataclass(frozen=True)
class ResolvedReference:
    """The Passage a reference such as `Note 5` names, and the Passages nested under it.

    `related` holds the other Passages inside the same part of the Filing, in
    Filing order: a Note's tables, an Item's subsections and risk factors.
    """

    passage: Passage
    related: tuple[Passage, ...]
