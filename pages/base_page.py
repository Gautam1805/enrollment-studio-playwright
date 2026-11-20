"""What every page object shares: the page, its path, and its main heading."""

from urllib.parse import urlparse

from playwright.sync_api import Locator, Page


class BasePage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def test_id(self, value: str) -> Locator:
        return self.page.get_by_test_id(value)

    def current_path(self) -> str:
        return urlparse(self.page.url).path or "/"

    def wait_for_path(self, path: str, timeout: float | None = None) -> None:
        self.page.wait_for_url(lambda url: (urlparse(url).path or "/") == path, timeout=timeout)

    @property
    def heading(self) -> Locator:
        """The page's main heading."""
        return self.page.locator("main h1, h1").first
