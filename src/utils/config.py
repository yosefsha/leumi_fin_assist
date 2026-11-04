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
# The fiscal year and filer of the shipped Filing (DEFAULT_FILING_PATH): Apple's FY2025 10-K.
DEFAULT_FILING_FISCAL_YEAR = "2025"
DEFAULT_FILING_COMPANY = "Apple Inc."

MAX_COMPANY_CHARS = 100

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class ConfigError(Exception):
    """The configuration is missing or invalid."""


class MissingSettingError(ConfigError):
    """A required setting has no value."""

    def __init__(self, name: str, reason: str = "") -> None:
        super().__init__(
            f"Required setting {name} is not set{f' ({reason})' if reason else ''}. "
            "Set it in the environment or in .env (see .env.example)."
        )
        self.name = name


@dataclass(frozen=True)
class FilingProfile:
    """Which Filing the agent answers from, and how the prompts and the CLI name it.

    It needs no API key, so `--help` and the menu can describe the configured
    company before the keys are checked. `suggested_questions_path` is `None` when
    no questions file is configured.
    """

    path: Path
    company: str
    fiscal_year: int
    suggested_questions_path: Path | None

    @property
    def is_shipped(self) -> bool:
        """Whether this is the Filing shipped in the repository (Apple's FY2025 10-K)."""
        return _is_shipped_filing(self.path)

    @classmethod
    def load(cls, env_file: Path = DEFAULT_ENV_FILE) -> "FilingProfile":
        """Load the profile from `env_file` (if present) overlaid by the process environment."""
        return cls.from_mapping(load_environment(env_file))

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "FilingProfile":
        """Build the profile from raw values keyed by environment variable name.

        `FILING_COMPANY` and `FILING_FISCAL_YEAR` default to the shipped Filing's,
        but only while `FILING_PATH` is the shipped Filing: for any other Filing
        they are required, so another company's 10-K is never described as Apple's
        FY2025 one. Raises `MissingSettingError` or `ConfigError` otherwise.
        """
        path = _project_path(_optional(values, "FILING_PATH", DEFAULT_FILING_PATH))
        if _is_shipped_filing(path):
            company = _optional(values, "FILING_COMPANY", DEFAULT_FILING_COMPANY)
            fiscal_year = _optional(values, "FILING_FISCAL_YEAR", DEFAULT_FILING_FISCAL_YEAR)
        else:
            reason = "FILING_PATH names a Filing other than the shipped one"
            company = _required(values, "FILING_COMPANY", reason)
            fiscal_year = _required(values, "FILING_FISCAL_YEAR", reason)
        questions = _optional(values, "SUGGESTED_QUESTIONS_PATH", "")
        return cls(
            path=path,
            company=_company(company),
            fiscal_year=_fiscal_year(fiscal_year),
            suggested_questions_path=_project_path(questions) if questions else None,
        )


@dataclass(frozen=True)
class Settings:
    """Validated runtime configuration for the agent."""

    anthropic_api_key: str = field(repr=False)
    tavily_api_key: str = field(repr=False)
    anthropic_model: str
    filing: FilingProfile
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
            filing=FilingProfile.from_mapping(values),
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


def _required(values: Mapping[str, str], name: str, reason: str = "") -> str:
    value = values.get(name, "").strip()
    if not value:
        raise MissingSettingError(name, reason)
    return value


def _optional(values: Mapping[str, str], name: str, default: str) -> str:
    return values.get(name, "").strip() or default


def _project_path(raw: str) -> Path:
    """Resolve a relative path against the repository root, so the CWD does not matter."""
    path = Path(raw).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _is_shipped_filing(path: Path) -> bool:
    """Whether `path` is the shipped Filing, however it is spelled (relative, `..`, a symlink)."""
    return path.resolve() == _project_path(DEFAULT_FILING_PATH).resolve()


def _log_level(raw: str) -> str:
    level = raw.upper()
    if level not in _LOG_LEVELS:
        raise ConfigError(f"LOG_LEVEL must be one of {', '.join(_LOG_LEVELS)}; got {raw!r}.")
    return level


def _fiscal_year(raw: str) -> int:
    """A four-digit fiscal year, e.g. `2025`."""
    if not (len(raw) == 4 and raw.isdigit() and raw[0] != "0"):
        raise ConfigError(
            f"FILING_FISCAL_YEAR must be a four-digit year such as 2025; got {raw!r}."
        )
    return int(raw)


def _company(raw: str) -> str:
    """The filer's name as the prompts and the CLI write it, e.g. `Apple Inc.`."""
    if len(raw) > MAX_COMPANY_CHARS or not raw.isprintable():
        raise ConfigError(
            f"FILING_COMPANY must be one line of at most {MAX_COMPANY_CHARS} printable "
            f"characters, such as 'Apple Inc.'; got {raw!r}."
        )
    return raw
