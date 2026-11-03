# Local embeddings with hybrid retrieval over Passages

Anthropic offers no embeddings API, and a reviewer running the project already needs two keys (the LLM provider and Tavily). The Filing also has long sections and wide financial tables that do not fit an embedding model's input as-is. We embed locally with fastembed running `BAAI/bge-small-en-v1.5` (ONNX, 384 dimensions, CPU only), fuse its results with BM25 using reciprocal rank fusion (RRF), and store vectors in a local Chroma collection.

## Considered Options

- **Voyage `voyage-finance-2`** — rejected: a third API key, a network dependency at index and query time, and per-token cost.
- **OpenAI `text-embedding-3-small`** — rejected: a third key and a third vendor.
- **sentence-transformers** — rejected: pulls in torch (~2 GB) to run the same model fastembed runs on ONNX.
- **Long-context models (`nomic-embed-text-v1.5`, `jina-embeddings-v2-base-en`)** — rejected: embedding a whole section into one vector blurs the distinct topics inside it, which is exactly what retrieval needs to tell apart.
- **`bge-base-en-v1.5`** — not chosen now: same 512-token input limit, larger and slower; it is the upgrade path if recall proves too weak.

## Limitations

- The model accepts 512 tokens and silently truncates anything longer, so an oversized input loses its tail without an error.
- Dense embeddings are weak at exact financial terms ("Research and development", "Gross margin percentage").

## Strategy

- Index Entries are at most 350 tokens, leaving headroom for the Section Path prefix each one carries, and never cross a heading. A hit returns the full Passage, not the Index Entry.
- Tables are indexed as Table Cards; a large table is split by row groups, with the column headers repeated in each card.
- The index build raises if any Index Entry exceeds 512 model tokens, rather than letting truncation pass silently.
- BM25 runs alongside the dense search to recover exact-term matches.

## Consequences

- First run downloads the model (~130 MB).
- Changing the Filing requires re-indexing.
- Swapping the embedding model is a re-index only: retrieval depends on an `Embedder` protocol, not on fastembed.
