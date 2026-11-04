"""Load agent prompts from text files under `prompts/`."""

import re
from collections.abc import Mapping
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


def load_tool_description(
    tool_name: str, values: Mapping[str, str] | None = None, prompts_dir: Path = PROMPTS_DIR
) -> str:
    """Return the `## <tool_name>` section of `<prompts_dir>/tool_descriptions.txt`.

    A section runs from its `## <tool_name>` heading line to the next `## ` heading
    or the end of the file; surrounding whitespace is stripped. Its `{{placeholders}}`
    are filled from `values` as `render_prompt` fills a prompt's, and must match
    them the same way. Raises `ToolDescriptionNotFoundError` when the section is
    missing or empty, and `PromptPlaceholderError` on a placeholder mismatch.
    """
    text = load_prompt("tool_descriptions", prompts_dir)
    for section in re.split(r"^## +", text, flags=re.MULTILINE)[1:]:
        heading, _, body = section.partition("\n")
        if heading.strip() == tool_name and body.strip():
            return fill_placeholders(body.strip(), values or {}, f"tool description {tool_name!r}")
    raise ToolDescriptionNotFoundError(
        f"No description for tool {tool_name!r} in {prompts_dir / 'tool_descriptions.txt'}."
    )


_PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


class PromptPlaceholderError(ValueError):
    """A prompt's `{{placeholders}}` and the values supplied for it do not match."""


def render_prompt(name: str, values: Mapping[str, str], prompts_dir: Path = PROMPTS_DIR) -> str:
    """Return `load_prompt(name)` with each `{{key}}` replaced by `values[key]`.

    Raises `PromptPlaceholderError` when the prompt uses a placeholder with no
    value, or a value is supplied for a placeholder the prompt does not use, so a
    renamed placeholder fails at the first call instead of reaching the model.
    """
    return fill_placeholders(load_prompt(name, prompts_dir), values, f"Prompt {name!r}")


def fill_placeholders(text: str, values: Mapping[str, str], source: str) -> str:
    """Return `text` with each `{{key}}` replaced by `values[key]`.

    Raises `PromptPlaceholderError`, naming `source`, when `text` uses a
    placeholder with no value or a value is supplied for one it does not use.
    A value is inserted as-is: placeholders inside it are not expanded.
    """
    used = set(_PLACEHOLDER.findall(text))
    missing = used - values.keys()
    unused = values.keys() - used
    if missing or unused:
        raise PromptPlaceholderError(
            f"{source}: no value for {sorted(missing)}; unused values {sorted(unused)}."
        )
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)], text)
