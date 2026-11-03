"""Visible text and emphasis of the Filing's inline-styled HTML elements."""

import re
from collections.abc import Iterator

from bs4 import NavigableString, Tag

_WHITESPACE = re.compile(r"\s+")
_BOLD_WEIGHT = re.compile(r"bold|bolder|[6-9]00")


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace (including non-breaking spaces) to one space and trim."""
    return _WHITESPACE.sub(" ", text).strip()


def visible_text(element: Tag) -> str:
    """Return the text a reader sees in `element`, on one line.

    Only plain text nodes count (comments and other markup strings are skipped).
    Inline pieces (`<span>`, `ix:*` wrappers) are joined without a separator, so a
    figure split across tags (`(` + `321` + `)`) stays one token. Each `<br>` and
    each nested `<div>` boundary becomes a space, so a header such as
    `September 27,<br/>2025` reads `September 27, 2025`.
    """
    parts: list[str] = []
    for node in element.descendants:
        if isinstance(node, Tag):
            if node.name in ("br", "div"):
                parts.append(" ")
        elif type(node) is NavigableString:
            parts.append(str(node))
    return normalize_whitespace("".join(parts))


def emphasis(leaf: Tag) -> tuple[bool, bool]:
    """Return whether all visible text in `leaf` is (bold, italic), per its inline styles.

    The innermost declaration wins, so a `font-weight:400` span inside a bold div is
    not bold. An element with no visible text counts as neither.
    """
    strings = list(_visible_strings(leaf))
    bold = italic = bool(strings)
    for text in strings:
        bold = bold and _BOLD_WEIGHT.fullmatch(_innermost(text, leaf, "font-weight")) is not None
        italic = italic and _innermost(text, leaf, "font-style") == "italic"
    return bold, italic


def _visible_strings(leaf: Tag) -> Iterator[NavigableString]:
    for node in leaf.descendants:
        if type(node) is NavigableString and node.strip():
            yield node


def _innermost(text: NavigableString, leaf: Tag, prop: str) -> str:
    """The value of CSS `prop` closest to `text` among inline styles up to `leaf`, or ''."""
    for parent in text.parents:
        for declaration in parent.get("style", "").split(";"):
            name, _, value = declaration.partition(":")
            if name.strip().lower() == prop:
                return value.strip().lower()
        if parent is leaf:
            break
    return ""
