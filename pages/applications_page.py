"""The landing page after sign-in: the list of enrollment applications."""

import re
from enum import Enum

from playwright.sync_api import Locator, expect

from pages.base_page import BasePage
from pages.side_nav import SideNav


class Status(Enum):
    """The status chips: label, filter test-id and summary-card test-id.

    Test names come from the app itself; the summary cards reuse the same
    status ('In progress' cards count the drafts) plus one review card.
    """

    ALL = ("All", "csr-search-status-all", "summary-total")
    IN_PROGRESS = ("In progress", "csr-search-status-draft", "summary-draft")
    SUBMITTED = ("Submitted", "csr-search-status-submitted", "summary-submitted")
    ENROLLED = ("Enrolled", "csr-search-status-enrolled", "summary-enrolled")
    REJECTED = ("Rejected", "csr-search-status-rejected", "summary-rejected")
    EXPIRED = ("Expired", "csr-search-status-expired", "summary-expired")

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def filter_id(self) -> str:
        return self.value[1]

    @property
    def summary_id(self) -> str:
        return self.value[2]


#: The live region says this while the list re-runs a filter or a search.
UPDATING_TEXT = "Updating results..."

#: The note the list shows when nothing matches the current filters.
EMPTY_MESSAGE = "No applications match"


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

    # ---- the toolbar: status filter and search ---------------------------

    def status_filter(self, status: Status) -> Locator:
        """The chip that filters the list by one status."""
        return self.test_id(status.filter_id)

    @property
    def search(self) -> Locator:
        """The search box (first name, last name or member number)."""
        return self.test_id("csr-search-query")

    def filter_by_status(self, status: Status) -> "ApplicationsPage":
        """Click a status chip and wait for the list to refresh."""
        self.status_filter(status).click()
        return self.wait_for_results()

    def set_search(self, term: str) -> "ApplicationsPage":
        """Fill the search box and wait for the list to refresh."""
        self.search.fill(term)
        return self.wait_for_results()

    def clear_search(self) -> "ApplicationsPage":
        """Empty the search box and wait for the list to refresh."""
        self.search.fill("")
        return self.wait_for_results()

    def wait_for_results(self) -> "ApplicationsPage":
        """Every change re-runs the list backend and shows 'Updating
        results...' until it is done. Wait for either the settled total or
        the empty state, whichever this change ends up with."""
        settled = self.result_range.or_(self.empty_state)
        expect(settled.filter(has_not_text=UPDATING_TEXT)).to_be_visible()
        return self

    # ---- the summary cards ------------------------------------------------

    @property
    def summary(self) -> Locator:
        """The strip of status-count cards at the top of the page."""
        return self.page.get_by_role("region", name="Application summary")

    def summary_count(self, status: Status) -> Locator:
        """The number on the card for this status."""
        return self.test_id(status.summary_id)

    @property
    def awaiting_review_count(self) -> Locator:
        return self.test_id("summary-review")

    def summary_label(self, label: str) -> Locator:
        """The card labelled `label` (e.g. 'In progress', 'Awaiting review')."""
        return self.summary.get_by_text(label, exact=True)

    # ---- the table ---------------------------------------------------------

    def column_header(self, name: str) -> Locator:
        """A headed column of the applications table (e.g. 'Applicant')."""
        return self.page.get_by_role("columnheader", name=name)

    @property
    def rows(self) -> Locator:
        return self.table.locator("tbody tr")

    def row_for(self, text: str) -> Locator:
        """Every row that mentions `text` somewhere in its cells."""
        return self.rows.filter(has_text=text)

    def row_applicant(self, row: Locator) -> Locator:
        """The applicant's cell of `row` (name plus e-mail or member no.)."""
        return row.locator("td").first

    def row_link(self, row: Locator) -> Locator:
        """`row`'s link into the application itself — its stable identity,
        unlike its text, which applicants can share."""
        return self.row_applicant(row).get_by_role("link")

    def row_ssn(self, row: Locator) -> Locator:
        """The SSN cell of `row`; the list only ever shows it masked."""
        return row.locator("td").nth(1)

    def row_status(self, row: Locator) -> Locator:
        """The status badge of `row` (4th column; one badge per cell)."""
        return row.locator("td").nth(3).locator('[data-slot="badge"]').first

    @property
    def empty_state(self) -> Locator:
        """The 'No applications match' note shown instead of the table."""
        return self.page.locator("main").get_by_text(EMPTY_MESSAGE)

    # ---- the pager ----------------------------------------------------------

    @property
    def result_range(self) -> Locator:
        """'1-25 of 146 applications' while a list exists; live region."""
        return self.test_id("applications-pager-range")

    @property
    def pager_page(self) -> Locator:
        """The 'Page X of Y' read-out."""
        return self.test_id("applications-pager-page")

    @property
    def pager_previous(self) -> Locator:
        return self.test_id("applications-pager-previous")

    @property
    def pager_next(self) -> Locator:
        return self.test_id("applications-pager-next")

    def go_next(self) -> "ApplicationsPage":
        self.pager_next.click()
        return self.wait_for_results()

    def go_previous(self) -> "ApplicationsPage":
        self.pager_previous.click()
        return self.wait_for_results()

    def show_row(self, text: str) -> None:
        """Page forward until the list shows a row mentioning `text`, the
        way a human finds one that no longer sits on page 1. `go_next`
        stops itself on the last page; the caller asserts on the row."""
        while self.row_for(text).count() == 0 and self.pager_next.is_enabled():
            self.go_next()

    def result_count(self) -> int:
        """The total the pager reports for the current filters (0 if empty)."""
        if self.result_range.count() == 0:
            return 0
        match = re.search(r"of\s+(\d+)\s+(?:matching\s+)?applications", self.result_range.inner_text())
        return int(match.group(1)) if match else 0

    @property
    def nav(self) -> SideNav:
        return SideNav(self.page)
