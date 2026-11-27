"""One error type for every /crawl failure.

`detail` is safe to return: no key, no raw model reply, no page content.
"""

from app.deps import ApiError


class CrawlError(ApiError):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(status_code, detail, code)
