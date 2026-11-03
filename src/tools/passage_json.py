"""How `get_passage` lists the Passages related to the one it returns."""

from typing import Any

from utils.passage import Passage, PassageKind


def passage_outline_json(passage: Passage) -> dict[str, Any]:
    """A one-line listing of a Passage, without its content, to fetch it later by ID.

    A table's `title` is its caption, or its heading when it has none: the same
    text as the `_[Table: …]_` marker that stands for it in the surrounding text.
    Any other Passage's `title` is its Section Path below the Item.
    """
    return {
        "passage_id": passage.passage_id,
        "kind": passage.kind.value,
        "page": passage.page,
        "title": _table_marker_text(passage)
        if passage.kind is PassageKind.TABLE
        else " > ".join(passage.section_path[1:]) or passage.section_path_text,
    }


def _table_marker_text(passage: Passage) -> str:
    """The text the parser writes in the table's `_[Table: …]_` marker: caption or heading.

    A table Passage's content is `## <heading>`, then its caption paragraph if it
    has one, then the Markdown table.
    """
    heading, _, rest = passage.content.partition("\n\n")
    caption = rest.partition("\n\n")[0]
    if caption and not caption.startswith("|"):
        return caption
    return heading.removeprefix("## ")
