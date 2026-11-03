"""The `TokenCounter` port: measures text in an embedding model's tokens."""

from typing import Protocol


class TokenCounter(Protocol):
    """Counts the model tokens a text occupies, special tokens included, never truncating."""

    def count_tokens(self, text: str) -> int: ...
