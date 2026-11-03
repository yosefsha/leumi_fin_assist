"""`Embedder` and `TokenCounter` backed by a local fastembed (ONNX) model (ADR-0002)."""

from collections.abc import Sequence
from pathlib import Path

from fastembed import TextEmbedding
from tokenizers import Tokenizer

from utils.embedder import EmbedderError, Vector

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
"""The instruction BAAI recommends prefixing to short retrieval queries for bge v1.5 models."""


class FastEmbedEmbedder:
    """Embeds locally with fastembed; also counts tokens with the model's own tokenizer.

    The model is downloaded into `cache_dir` on first use (~130 MB for the
    default model) and loaded from there afterwards. Token counts come from an
    untruncated copy of the model's tokenizer, so an over-long text is measured
    at its real length instead of being capped at the model's limit.
    """

    def __init__(
        self,
        cache_dir: Path,
        model_name: str = DEFAULT_MODEL,
        query_instruction: str = BGE_QUERY_INSTRUCTION,
    ) -> None:
        try:
            self._model = TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))
        except (OSError, ValueError, RuntimeError) as error:
            raise EmbedderError(
                f"Cannot load the embedding model {model_name} into {cache_dir}: {error}"
            ) from error
        self._model_name = model_name
        self._query_instruction = query_instruction
        self._tokenizer, self._max_input_tokens = self._untruncated_tokenizer()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def max_input_tokens(self) -> int:
        return self._max_input_tokens

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        try:
            return [tuple(vector.tolist()) for vector in self._model.passage_embed(list(texts))]
        except (OSError, ValueError, RuntimeError) as error:
            raise EmbedderError(f"Embedding {len(texts)} documents failed: {error}") from error

    def embed_query(self, text: str) -> Vector:
        try:
            vectors = list(self._model.query_embed(self._query_instruction + text))
        except (OSError, ValueError, RuntimeError) as error:
            raise EmbedderError(f"Embedding the query failed: {error}") from error
        return tuple(vectors[0].tolist())

    def count_tokens(self, text: str) -> int:
        return len(self._tokenizer.encode(text).ids)

    def _untruncated_tokenizer(self) -> tuple[Tokenizer, int]:
        """Copy the model's tokenizer without truncation or padding; read its input limit."""
        source = getattr(self._model.model, "tokenizer", None)
        if not isinstance(source, Tokenizer) or not source.truncation:
            raise EmbedderError(
                f"The fastembed model {self._model_name} exposes no truncating tokenizer, "
                "so Index Entry lengths cannot be checked against its input limit."
            )
        max_input_tokens = int(source.truncation["max_length"])
        tokenizer = Tokenizer.from_str(source.to_str())
        tokenizer.no_truncation()
        tokenizer.no_padding()
        return tokenizer, max_input_tokens
