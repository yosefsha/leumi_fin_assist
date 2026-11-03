"""A web search result as the citation layer sees it."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WebResult:
    """One web page returned by a search, citable by its URL.

    `published_date` is the date the source reports for the page, as the source
    wrote it, or `None` when the source gives none. A blank title or date is
    normalised to the empty string / `None`; a blank URL is rejected, because a
    web Citation is its URL.
    """

    url: str
    title: str
    content: str
    published_date: str | None = None

    def __post_init__(self) -> None:
        url = self.url.strip()
        if not url:
            raise ValueError("A WebResult needs a non-blank URL.")
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "title", self.title.strip())
        date = self.published_date.strip() if self.published_date else ""
        object.__setattr__(self, "published_date", date or None)
