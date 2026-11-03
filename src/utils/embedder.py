"""The `Embedder` port: turns text into dense vectors for retrieval (ADR-0002)."""

from collections.abc import Sequence
from typing import Protocol

Vector = tuple[float, ...]
"""A dense embedding."""


class EmbedderError(Exception):
    """The embedding model could not be loaded or failed to embed."""


class Embedder(Protocol):
    """A dense text-embedding model.

    Documents and queries are embedded separately because retrieval models may
    treat them differently (e.g. an instruction prefix on short queries). Inputs
    longer than `max_input_tokens` would be truncated by the model, so callers
    check lengths with a `TokenCounter` before embedding. Raises `EmbedderError`.
    """

    @property
    def model_name(self) -> str:
        """Identifies the model; an index built with another model must be rebuilt."""
        ...

    @property
    def max_input_tokens(self) -> int:
        """The longest input, in model tokens, embedded without truncation."""
        ...

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        """Embed texts to be searched, one vector per text, in order."""
        ...

    def embed_query(self, text: str) -> Vector:
        """Embed a search query."""
        ...
