"""Wire a `FilingIndexLoader` the way `open_filing_index` does, with each port injectable."""

from utils.chunker import ENTRY_TOKEN_BUDGET, Chunker
from utils.embedder import Embedder
from utils.filing_index_loader import FilingIndexLoader
from utils.filing_parser import FilingParser
from utils.index_store import IndexStore
from utils.table_card_builder import TableCardBuilder
from utils.text_packer import TextPacker
from utils.token_counter import TokenCounter


def make_loader(
    embedder: Embedder,
    token_counter: TokenCounter,
    store: IndexStore,
    entry_budget: int = ENTRY_TOKEN_BUDGET,
) -> FilingIndexLoader:
    """A loader over `store` that packs Index Entry excerpts up to `entry_budget` tokens."""
    packer = TextPacker(token_counter, entry_budget)
    return FilingIndexLoader(
        parser=FilingParser(),
        chunker=Chunker(packer, TableCardBuilder(packer)),
        embedder=embedder,
        token_counter=token_counter,
        store=store,
    )
