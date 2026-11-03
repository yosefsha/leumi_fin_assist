"""Wire the Filing index from `Settings`: the one place concrete adapters are chosen."""

from utils.chroma_index_store import ChromaIndexStore
from utils.chunker import ENTRY_TOKEN_BUDGET, Chunker
from utils.config import Settings
from utils.fastembed_embedder import FastEmbedEmbedder
from utils.filing_index import FilingIndex
from utils.filing_index_loader import FilingIndexLoader
from utils.filing_parser import FilingParser
from utils.table_card_builder import TableCardBuilder
from utils.text_packer import TextPacker

MODELS_SUBDIR = "models"
STORE_SUBDIR = "chroma"


def open_filing_index(settings: Settings, force_rebuild: bool = False) -> FilingIndex:
    """Load (building if needed) the hybrid index of `settings.filing_path` under `INDEX_DIR`.

    The embedding model is cached in `INDEX_DIR/models`, the Chroma store lives in
    `INDEX_DIR/chroma`. `force_rebuild` backs the CLI's `--rebuild-index`.
    """
    embedder = FastEmbedEmbedder(cache_dir=settings.index_dir / MODELS_SUBDIR)
    packer = TextPacker(embedder, ENTRY_TOKEN_BUDGET)
    loader = FilingIndexLoader(
        parser=FilingParser(),
        chunker=Chunker(packer, TableCardBuilder(packer)),
        embedder=embedder,
        token_counter=embedder,
        store=ChromaIndexStore(settings.index_dir / STORE_SUBDIR),
    )
    return loader.load(settings.filing_path, force_rebuild=force_rebuild)
