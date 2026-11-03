"""Wire the Filing index from `Settings`: the one place concrete adapters are chosen."""

from utils.chroma_index_store import ChromaIndexStore
from utils.chunker import ENTRY_TOKEN_BUDGET, Chunker
from utils.config import Settings
from utils.embedder import Embedder, EmbedderError
from utils.fastembed_embedder import FastEmbedEmbedder
from utils.filing_index import FilingIndex
from utils.filing_index_loader import FilingIndexLoader, IndexEntryTooLongError
from utils.filing_parser import FilingParseError, FilingParser
from utils.index_store import IndexStore, IndexStoreError
from utils.table_card_builder import TableCardBuilder
from utils.text_packer import TextPacker
from utils.token_counter import TokenCounter

MODELS_SUBDIR = "models"
STORE_SUBDIR = "chroma"

# Everything `open_filing_index` raises when the index cannot be opened or built.
INDEX_LOAD_ERRORS: tuple[type[Exception], ...] = (
    FilingParseError,
    IndexEntryTooLongError,
    EmbedderError,
    IndexStoreError,
)


def open_filing_index(settings: Settings, force_rebuild: bool = False) -> FilingIndex:
    """Load (building if needed) the hybrid index of `settings.filing_path` under `INDEX_DIR`.

    The embedding model is cached in `INDEX_DIR/models`, the Chroma store lives in
    `INDEX_DIR/chroma`. `force_rebuild` backs the CLI's `--rebuild-index`.
    Raises one of `INDEX_LOAD_ERRORS` when the index cannot be opened or built.
    """
    embedder = FastEmbedEmbedder(cache_dir=settings.index_dir / MODELS_SUBDIR)
    loader = build_filing_index_loader(
        embedder=embedder,
        token_counter=embedder,
        store=ChromaIndexStore(settings.index_dir / STORE_SUBDIR),
    )
    return loader.load(settings.filing_path, force_rebuild=force_rebuild)


def build_filing_index_loader(
    embedder: Embedder,
    token_counter: TokenCounter,
    store: IndexStore,
    entry_budget: int = ENTRY_TOKEN_BUDGET,
) -> FilingIndexLoader:
    """Assemble the parse → chunk → length-check → embed → store pipeline over the given ports.

    `entry_budget` is the token budget of each Index Entry's excerpt.
    """
    packer = TextPacker(token_counter, entry_budget)
    return FilingIndexLoader(
        parser=FilingParser(),
        chunker=Chunker(packer, TableCardBuilder(packer)),
        embedder=embedder,
        token_counter=token_counter,
        store=store,
    )
