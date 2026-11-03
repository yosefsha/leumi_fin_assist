"""Pack text units into pieces that fit a token budget, splitting oversized units."""

import re
from collections.abc import Iterable, Sequence

from utils.token_counter import TokenCounter

_SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")
_PARAGRAPH_SEPARATOR = "\n\n"


class TextPacker:
    """Greedily joins whole paragraphs into pieces of at most `budget` tokens.

    A paragraph that alone exceeds the budget is split at sentence ends, and a
    sentence that still exceeds it is split between words, so every piece fits.
    """

    def __init__(self, token_counter: TokenCounter, budget: int) -> None:
        if budget < 1:
            raise ValueError(f"The token budget must be positive; got {budget}.")
        self._token_counter = token_counter
        self._budget = budget

    def fits(self, text: str) -> bool:
        """Whether `text` is within the budget."""
        return self._token_counter.count_tokens(text) <= self._budget

    def pack(self, paragraphs: Sequence[str]) -> list[str]:
        """Join `paragraphs` (in order, blank-line separated) into pieces within the budget."""
        units = [unit for paragraph in paragraphs for unit in self._fitting_units(paragraph)]
        return self._join(units, _PARAGRAPH_SEPARATOR)

    def _fitting_units(self, paragraph: str) -> Iterable[str]:
        if self.fits(paragraph):
            yield paragraph
            return
        for sentence in self._join(_SENTENCE_END.split(paragraph), " "):
            if self.fits(sentence):
                yield sentence
            else:
                yield from self._join(sentence.split(), " ")

    def _join(self, units: Sequence[str], separator: str) -> list[str]:
        """Greedily join `units` with `separator` while the joined text stays within budget.

        A single unit over the budget is kept whole as its own piece; `_fitting_units`
        splits such units further before packing paragraphs.
        """
        pieces: list[str] = []
        current: list[str] = []
        for unit in units:
            if not unit:
                continue
            if current and not self.fits(separator.join([*current, unit])):
                pieces.append(separator.join(current))
                current = []
            current.append(unit)
        if current:
            pieces.append(separator.join(current))
        return pieces
