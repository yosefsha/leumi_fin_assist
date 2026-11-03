"""In-memory `Embedder` fake: the same unit vector for every text, no model to load."""

from collections.abc import Sequence

from utils.embedder import Vector

_VECTOR: Vector = (1.0, 0.0, 0.0)


class ConstantEmbedder:
    """Embeds instantly, for tests about when the index is (re)built rather than what it finds.

    `model_name` differs from the real model's, so an index built with this fake
    never matches the fingerprint of one built with the real model.
    """

    def __init__(self, max_input_tokens: int = 512) -> None:
        self._max_input_tokens = max_input_tokens

    @property
    def model_name(self) -> str:
        return "constant-test-embedder"

    @property
    def max_input_tokens(self) -> int:
        return self._max_input_tokens

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        return [_VECTOR for _ in texts]

    def embed_query(self, text: str) -> Vector:
        return _VECTOR
