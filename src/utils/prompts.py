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
