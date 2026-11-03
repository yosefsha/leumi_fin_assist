"""`Embedder` spy: delegates to another `Embedder` and counts the document-embedding calls."""

from collections.abc import Sequence

from utils.embedder import Embedder, Vector


class CountingEmbedder:
    """Wraps `inner`; `document_calls` is how many times `embed_documents` ran (a build)."""

    def __init__(self, inner: Embedder) -> None:
        self._inner = inner
        self.document_calls = 0

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    @property
    def max_input_tokens(self) -> int:
        return self._inner.max_input_tokens

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        self.document_calls += 1
        return self._inner.embed_documents(texts)

    def embed_query(self, text: str) -> Vector:
        return self._inner.embed_query(text)
