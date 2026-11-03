"""The Filing's hybrid index (issue #4, PR #20): the 512-token guard, reuse and rebuilds, ranking.

The real embedding model builds the session's index once (`filing_index` in
conftest). Tests about *when* the index is rebuilt use the instant
`ConstantEmbedder` fake, so they do not re-embed the Filing.
"""

from pathlib import Path

import pytest

from fakes.constant_embedder import ConstantEmbedder
from fakes.counting_embedder import CountingEmbedder
from fakes.in_memory_index_store import InMemoryIndexStore
from utils.fastembed_embedder import FastEmbedEmbedder
from utils.filing_index import FilingIndex, UnknownItemError
from utils.filing_index_factory import build_filing_index_loader
from utils.filing_index_loader import IndexEntryTooLongError
from utils.passage import Passage


def test_build_covers_every_passage_within_the_model_limit(
    filing_index: FilingIndex,
    index_store: InMemoryIndexStore,
    embedder: FastEmbedEmbedder,
    passages: tuple[Passage, ...],
) -> None:
    entries = index_store.entries()
    assert len(entries) == filing_index.entry_count > 0
    assert max(embedder.count_tokens(entry.text) for entry in entries) <= 512
    assert {entry.passage_id for entry in entries} == {p.passage_id for p in passages}


def test_an_entry_over_the_model_limit_fails_the_build(
    embedder: FastEmbedEmbedder, filing_path: Path
) -> None:
    loader = build_filing_index_loader(embedder, embedder, InMemoryIndexStore(), entry_budget=2000)
    with pytest.raises(IndexEntryTooLongError) as raised:
        loader.load(filing_path)
    assert raised.value.tokens > raised.value.limit == 512


def test_a_second_start_reuses_the_stored_index(
    filing_index: FilingIndex,
    embedder: FastEmbedEmbedder,
    index_store: InMemoryIndexStore,
    filing_path: Path,
) -> None:
    counting = CountingEmbedder(embedder)
    reloaded = build_filing_index_loader(counting, embedder, index_store).load(filing_path)
    assert counting.document_calls == 0
    assert reloaded.entry_count == filing_index.entry_count


@pytest.fixture
def constant_store(embedder: FastEmbedEmbedder, filing_path: Path) -> InMemoryIndexStore:
    """A store already holding a current index of the Filing, built with `ConstantEmbedder`."""
    store = InMemoryIndexStore()
    build_filing_index_loader(ConstantEmbedder(), embedder, store).load(filing_path)
    return store


def test_a_changed_filing_is_rebuilt(
    constant_store: InMemoryIndexStore,
    embedder: FastEmbedEmbedder,
    filing_path: Path,
    tmp_path: Path,
) -> None:
    changed = tmp_path / filing_path.name
    changed.write_bytes(filing_path.read_bytes() + b"\n<!-- amended -->\n")
    counting = CountingEmbedder(ConstantEmbedder())

    build_filing_index_loader(counting, embedder, constant_store).load(changed)
    assert counting.document_calls == 1

    build_filing_index_loader(counting, embedder, constant_store).load(changed)
    assert counting.document_calls == 1


def test_force_rebuild_rebuilds_a_current_index(
    constant_store: InMemoryIndexStore, embedder: FastEmbedEmbedder, filing_path: Path
) -> None:
    counting = CountingEmbedder(ConstantEmbedder())
    build_filing_index_loader(counting, embedder, constant_store).load(
        filing_path, force_rebuild=True
    )
    assert counting.document_calls == 1


def test_risk_factors_query_ranks_item_1a_first(filing_index: FilingIndex) -> None:
    hits = filing_index.search("risk factors")
    assert hits[0].passage.item == "Item 1A"


def test_item_filter_returns_only_that_item(filing_index: FilingIndex) -> None:
    hits = filing_index.search("research and development", item="Item 8")
    assert hits
    assert {hit.passage.item for hit in hits} == {"Item 8"}


def test_unknown_item_filter_raises(filing_index: FilingIndex) -> None:
    with pytest.raises(UnknownItemError, match="Item 99"):
        filing_index.search("revenue", item="Item 99")
