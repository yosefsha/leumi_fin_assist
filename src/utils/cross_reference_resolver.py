"""Resolve cross-references such as `Note 5` or `Part II, Item 7` to Filing Passages."""

import re
from collections.abc import Iterable

from utils.filing_items import ITEM_PARTS, parse_item_label, short_item_label, sorted_items
from utils.passage import Passage, PassageKind
from utils.resolved_reference import ResolvedReference

REFERENCE_FORMS = "'Note 5', 'Item 1A', 'Part II, Item 7', or a passage_id such as 'item-8-021'"
"""The reference forms `resolve` accepts, as written in an error message."""

_NOTE_REFERENCE = re.compile(r"note\s+(\d{1,3})", re.IGNORECASE)
_PART_ITEM_REFERENCE = re.compile(
    r"(?:part\s+(iv|i{1,3})\s*[,\-–—]?\s*)?(item\s*\d{1,2}[a-z]?\.?)", re.IGNORECASE
)
_NOTE_HEADING = re.compile(r"Note (\d{1,3})\b")


class UnknownReferenceError(ValueError):
    """A reference names nothing in the Filing, or is not in an accepted form."""


class CrossReferenceResolver:
    """Finds the Passage a cross-reference names.

    Accepted forms: `Note <n>` (the whole Note), `Item <id>` optionally preceded
    by its Part (`Part II, Item 7`; the Item's opening Passage), and a
    `passage_id`. Matching ignores case and extra whitespace.
    """

    def __init__(self, passages: Iterable[Passage]) -> None:
        self._passages = tuple(passages)
        self._by_id = {passage.passage_id.casefold(): passage for passage in self._passages}
        self._notes: dict[int, Passage] = {}
        self._item_openings: dict[str, Passage] = {}
        for passage in self._passages:
            self._item_openings.setdefault(passage.item, passage)
            if passage.kind is PassageKind.NOTE and len(passage.section_path) > 1:
                heading = _NOTE_HEADING.match(passage.section_path[1])
                if heading is not None:
                    self._notes.setdefault(int(heading.group(1)), passage)

    def resolve(self, reference: str) -> ResolvedReference:
        """Return the Passage `reference` names and the Passages nested under it.

        Raises `UnknownReferenceError` for a reference in no accepted form, a Note
        or Item the Filing lacks, or a Part that does not contain the Item.
        """
        text = " ".join(reference.split())
        if not text:
            raise UnknownReferenceError(f"The reference is empty. Use {REFERENCE_FORMS}.")
        passage = self._by_id.get(text.casefold())
        if passage is not None:
            return self._with_related(passage, passage.section_path)
        if note := _NOTE_REFERENCE.fullmatch(text):
            return self._resolve_note(int(note.group(1)))
        if part_item := _PART_ITEM_REFERENCE.fullmatch(text):
            part, item_label = part_item.groups()
            return self._resolve_item(item_label, part)
        raise UnknownReferenceError(
            f"Cannot resolve reference {reference!r}. Use {REFERENCE_FORMS}."
        )

    def _resolve_note(self, number: int) -> ResolvedReference:
        passage = self._notes.get(number)
        if passage is None:
            known = ", ".join(str(n) for n in sorted(self._notes)) or "none"
            raise UnknownReferenceError(
                f"The Filing has no Note {number}; its Notes are {known}. Use {REFERENCE_FORMS}."
            )
        return self._with_related(passage, passage.section_path[:2])

    def _resolve_item(self, item_label: str, part: str | None) -> ResolvedReference:
        item = parse_item_label(item_label)
        passage = self._item_openings.get(item) if item is not None else None
        if item is None or passage is None:
            known = ", ".join(
                short_item_label(name)
                for name in sorted_items(self._item_openings)
                if name in ITEM_PARTS
            )
            raise UnknownReferenceError(
                f"The Filing has no {item or item_label.strip()}; its Items are {known}. "
                f"Use {REFERENCE_FORMS}."
            )
        if part is not None and ITEM_PARTS.get(item) != part.upper():
            actual = ITEM_PARTS.get(item)
            where = f"in Part {actual}" if actual else "not in a numbered Part"
            raise UnknownReferenceError(
                f"{item} is {where}, not Part {part.upper()}. Use {REFERENCE_FORMS}."
            )
        return self._with_related(passage, (item,))

    def _with_related(self, passage: Passage, scope: tuple[str, ...]) -> ResolvedReference:
        related = tuple(
            other
            for other in self._passages
            if other is not passage and other.section_path[: len(scope)] == scope
        )
        return ResolvedReference(passage, related)
