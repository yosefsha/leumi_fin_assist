"""Runtime configuration loaded from the environment and an optional `.env` file.

API keys are secrets: they are excluded from the `Settings` repr and never appear
in an error message or a log line.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"
DEFAULT_FILING_PATH = "data/apple_10k_2025.htm"
DEFAULT_INDEX_DIR = ".index"
DEFAULT_LOG_LEVEL = "INFO"

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class ConfigError(Exception):
    """The configuration is missing or invalid."""


class MissingSettingError(ConfigError):
    """A required setting has no value."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"Required setting {name} is not set. "
            "Set it in the environment or in .env (see .env.example)."
        )
        self.name = name


@dataclass(frozen=True)
class Settings:
    """Validated runtime configuration for the agent."""

    anthropic_api_key: str = field(repr=False)
    tavily_api_key: str = field(repr=False)
    anthropic_model: str
    filing_path: Path
    index_dir: Path
    log_level: str

    @classmethod
    def load(cls, env_file: Path = DEFAULT_ENV_FILE) -> "Settings":
        """Load settings from `env_file` (if present) overlaid by the process environment.

        A blank environment variable does not override a value set in `env_file`.
        """
        return cls.from_mapping(load_environment(env_file))

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "Settings":
        """Build settings from raw string values keyed by environment variable name.

        Raises `MissingSettingError` for an absent or blank required key, and
        `ConfigError` for an invalid value.
        """
        return cls(
            anthropic_api_key=_required(values, "ANTHROPIC_API_KEY"),
            tavily_api_key=_required(values, "TAVILY_API_KEY"),
            anthropic_model=_optional(values, "ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL),
            filing_path=_project_path(_optional(values, "FILING_PATH", DEFAULT_FILING_PATH)),
            index_dir=_project_path(_optional(values, "INDEX_DIR", DEFAULT_INDEX_DIR)),
            log_level=_log_level(_optional(values, "LOG_LEVEL", DEFAULT_LOG_LEVEL)),
        )


def load_environment(env_file: Path = DEFAULT_ENV_FILE) -> dict[str, str]:
    """Return the non-blank variables of `env_file` (if present) overlaid by the environment.

    A blank environment variable does not override a value set in `env_file`.
    """
    file_values = {k: v for k, v in dotenv_values(env_file).items() if v and v.strip()}
    env_values = {k: v for k, v in os.environ.items() if v.strip()}
    return {**file_values, **env_values}


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise MissingSettingError(name)
    return value


def _optional(values: Mapping[str, str], name: str, default: str) -> str:
    return values.get(name, "").strip() or default


def _project_path(raw: str) -> Path:
    """Resolve a relative path against the repository root, so the CWD does not matter."""
    path = Path(raw).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _log_level(raw: str) -> str:
    level = raw.upper()
    if level not in _LOG_LEVELS:
        raise ConfigError(f"LOG_LEVEL must be one of {', '.join(_LOG_LEVELS)}; got {raw!r}.")
    return level
