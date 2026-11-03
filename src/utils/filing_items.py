"""How Items of a Form 10-K are named, ordered and grouped into Parts."""

import re
from collections.abc import Iterable

ITEM_PREFIX = "Item "

# "1A", "item 1a", "Item 1A." -> number "1", letter "A".
_ITEM_LABEL = re.compile(r"(?:item\s*)?(\d{1,2})([a-z]?)\.?", re.IGNORECASE)

_ITEMS_BY_PART = {
    "I": ("1", "1A", "1B", "1C", "2", "3", "4"),
    "II": ("5", "6", "7", "7A", "8", "9", "9A", "9B", "9C"),
    "III": ("10", "11", "12", "13", "14"),
    "IV": ("15", "16"),
}

ITEM_PARTS: dict[str, str] = {
    f"{ITEM_PREFIX}{item}": part for part, items in _ITEMS_BY_PART.items() for item in items
}
"""The Part of Form 10-K each Item belongs to (Form 10-K General Instructions)."""


def parse_item_label(raw: str) -> str | None:
    """Return the canonical Item name for `raw` (`"1a"`, `"Item 1A"` -> `"Item 1A"`).

    Returns `None` when `raw` is not shaped like an Item label.
    """
    match = _ITEM_LABEL.fullmatch(raw.strip())
    if match is None:
        return None
    number, letter = match.groups()
    return f"{ITEM_PREFIX}{int(number)}{letter.upper()}"


def short_item_label(item: str) -> str:
    """The form a tool argument uses: `"Item 1A"` -> `"1A"`; other names are unchanged."""
    return item.removeprefix(ITEM_PREFIX)


def sorted_items(items: Iterable[str]) -> list[str]:
    """`items` in Filing order: other names (the Front Matter) first, then Items by number."""
    return sorted(items, key=_item_order)


def _item_order(item: str) -> tuple[int, int, str]:
    match = _ITEM_LABEL.fullmatch(item)
    if match is None or not item.startswith(ITEM_PREFIX):
        return (0, 0, item)
    number, letter = match.groups()
    return (1, int(number), letter)
