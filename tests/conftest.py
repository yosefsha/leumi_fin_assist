"""Shared fixtures and the `RUN_LIVE_TESTS` gate for `live` tests (ADR-0004).

The Filing is parsed once and indexed once per run (session-scoped fixtures). The
embedding model is cached in `.index/models`, the same place the agent uses, so
it downloads at most once per machine (and once per CI cache key).
"""

from pathlib import Path

import pytest

from fakes.in_memory_index_store import InMemoryIndexStore
from live_switch import (
    SKIP_REASON,
    live_tests_enabled,
    missing_keys_message,
    missing_live_keys,
)
from utils.config import DEFAULT_FILING_PATH, DEFAULT_INDEX_DIR, PROJECT_ROOT, load_environment
from utils.fastembed_embedder import FastEmbedEmbedder
from utils.filing_index import FilingIndex
from utils.filing_index_factory import MODELS_SUBDIR, build_filing_index_loader
from utils.filing_parser import FilingParser
from utils.passage import Passage

FILING_PATH = PROJECT_ROOT / DEFAULT_FILING_PATH
MODEL_CACHE_DIR = PROJECT_ROOT / DEFAULT_INDEX_DIR / MODELS_SUBDIR


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip a `live` test unless `RUN_LIVE_TESTS=true`; then fail it if an API key is missing.

    Read from the environment or `.env`, like the agent's own settings.
    """
    if item.get_closest_marker("live") is None:
        return
    values = load_environment()
    if not live_tests_enabled(values):
        pytest.skip(SKIP_REASON)
    missing = missing_live_keys(values)
    if missing:
        pytest.fail(missing_keys_message(missing), pytrace=False)


@pytest.fixture(scope="session")
def filing_path() -> Path:
    """The Filing the agent answers from: Apple's FY2025 10-K."""
    return FILING_PATH


@pytest.fixture(scope="session")
def passages(filing_path: Path) -> tuple[Passage, ...]:
    """The Filing parsed into Passages, once per run."""
    return FilingParser().parse_file(filing_path)


@pytest.fixture(scope="session")
def embedder() -> FastEmbedEmbedder:
    """The real local embedding model (downloaded into `.index/models` on first use)."""
    return FastEmbedEmbedder(cache_dir=MODEL_CACHE_DIR)


@pytest.fixture(scope="session")
def index_store() -> InMemoryIndexStore:
    """The store the session's index is built into."""
    return InMemoryIndexStore()


@pytest.fixture(scope="session")
def filing_index(
    embedder: FastEmbedEmbedder, index_store: InMemoryIndexStore, filing_path: Path
) -> FilingIndex:
    """The Filing's hybrid index, built once per run with the real embedding model."""
    return build_filing_index_loader(embedder, embedder, index_store).load(filing_path)
