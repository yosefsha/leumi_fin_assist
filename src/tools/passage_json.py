"""How the Document QA tools show a Passage to the model."""

from typing import Any

from utils.passage import Passage, PassageKind

OUTLINE_TITLE_LENGTH = 160
"""Longest title shown for a Passage listed in an outline."""


def passage_to_json(passage: Passage) -> dict[str, Any]:
    """The whole Passage: its ID, location and Markdown content."""
    return {
        "passage_id": passage.passage_id,
        "section_path": passage.section_path_text,
        "page": passage.page,
        "page_approximate": passage.page_approximate,
        "kind": passage.kind.value,
        "content": passage.content,
    }


def passage_outline_json(passage: Passage) -> dict[str, Any]:
    """A one-line listing of a Passage, without its content, to fetch it later by ID."""
    return {
        "passage_id": passage.passage_id,
        "section_path": passage.section_path_text,
        "page": passage.page,
        "kind": passage.kind.value,
        "title": _title(passage),
    }


def _title(passage: Passage) -> str:
    """A table's caption (or column headers), or any other Passage's heading, on one line."""
    blocks = [block.strip() for block in passage.content.split("\n\n") if block.strip()]
    if not blocks:
        return passage.section_path[-1]
    title = blocks[0].lstrip("#")
    if passage.kind is PassageKind.TABLE and len(blocks) > 1:
        caption = blocks[1]
        if caption.startswith("|"):
            headers = [cell.strip() for cell in caption.splitlines()[0].strip("|").split("|")]
            caption = "Columns: " + ", ".join(cell for cell in headers if cell)
        title = caption
    title = " ".join(title.split())
    if len(title) > OUTLINE_TITLE_LENGTH:
        title = title[: OUTLINE_TITLE_LENGTH - 1].rstrip() + "…"
    return title
