"""The landing page after sign-in: the list of enrollment applications."""

from playwright.sync_api import expect

from pages.base_page import BasePage
from pages.side_nav import SideNav


class ApplicationsPage(BasePage):
    PATH = "/"

    @property
    def total(self):
        return self.test_id("summary-total")

    @property
    def table(self):
        return self.page.locator("main table")

    def open(self) -> "ApplicationsPage":
        self.page.goto(self.PATH)
        return self.wait_until_loaded()

    def wait_until_loaded(self) -> "ApplicationsPage":
        self.wait_for_path(self.PATH)
        expect(self.total).to_be_visible()
        return self

    @property
    def nav(self) -> SideNav:
        return SideNav(self.page)
