"""Load agent prompts from text files under `prompts/`."""

import re
from pathlib import Path

from utils.config import PROJECT_ROOT

PROMPTS_DIR = PROJECT_ROOT / "prompts"

# A prompt name is a bare file stem: no separators, so it cannot leave PROMPTS_DIR.
_PROMPT_NAME = re.compile(r"[a-z0-9_]+")


class PromptNotFoundError(Exception):
    """No prompt file exists for the requested name."""


def load_prompt(name: str, prompts_dir: Path = PROMPTS_DIR) -> str:
    """Return the text of `<prompts_dir>/<name>.txt`.

    Raises `ValueError` for a name that is not a lowercase file stem, and
    `PromptNotFoundError` when the file does not exist.
    """
    if not _PROMPT_NAME.fullmatch(name):
        raise ValueError(
            f"Invalid prompt name {name!r}: use lowercase letters, digits and underscores."
        )
    path = prompts_dir / f"{name}.txt"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise PromptNotFoundError(f"Prompt {name!r} not found: expected file {path}.") from error


class ToolDescriptionNotFoundError(PromptNotFoundError):
    """`tool_descriptions.txt` has no section for the requested tool."""


def load_tool_description(tool_name: str, prompts_dir: Path = PROMPTS_DIR) -> str:
    """Return the `## <tool_name>` section of `<prompts_dir>/tool_descriptions.txt`.

    A section runs from its `## <tool_name>` heading line to the next `## ` heading
    or the end of the file; surrounding whitespace is stripped. Raises
    `ToolDescriptionNotFoundError` when the section is missing or empty.
    """
    text = load_prompt("tool_descriptions", prompts_dir)
    for section in re.split(r"^## +", text, flags=re.MULTILINE)[1:]:
        heading, _, body = section.partition("\n")
        if heading.strip() == tool_name and body.strip():
            return body.strip()
    raise ToolDescriptionNotFoundError(
        f"No description for tool {tool_name!r} in {prompts_dir / 'tool_descriptions.txt'}."
    )
