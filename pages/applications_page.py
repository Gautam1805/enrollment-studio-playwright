"""The landing page after sign-in: the list of enrollment applications."""

from enum import Enum

from playwright.sync_api import Locator, expect

from pages.base_page import BasePage
from pages.side_nav import SideNav


class StatusOption(Enum):
    """A status filter choice: test-id suffix, filter label, summary card key."""

    ALL = ("all", "All", "total")
    IN_PROGRESS = ("draft", "In progress", "draft")
    SUBMITTED = ("submitted", "Submitted", "submitted")
    ENROLLED = ("enrolled", "Enrolled", "enrolled")
    REJECTED = ("rejected", "Rejected", "rejected")
    EXPIRED = ("expired", "Expired", "expired")

    @property
    def filter_test_id(self) -> str:
        """The data-testid suffix on the filter control for this status."""
        return self.value[0]

    @property
    def label(self) -> str:
        """What the filter button calls this status."""
        return self.value[1]

    @property
    def summary_key(self) -> str:
        """The test id suffix of the summary card counting this status."""
        return self.value[2]

    @property
    def badge(self) -> str:
        """How applications of this status read in the list's Status column."""
        return "Draft" if self is StatusOption.IN_PROGRESS else self.label


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

    # Status filter.

    STATUS_OPTIONS = (
        StatusOption.ALL,
        StatusOption.IN_PROGRESS,
        StatusOption.SUBMITTED,
        StatusOption.ENROLLED,
        StatusOption.REJECTED,
        StatusOption.EXPIRED,
    )
    #: Rows shown per page.
    PER_PAGE = 25

    def wait_until_loaded(self) -> "ApplicationsPage":
        self.wait_for_path(self.PATH)
        expect(self.total).to_be_visible()
        return self

    def status_option(self, option: StatusOption) -> Locator:
        """The "All/In progress/..." control that switches the list's status."""
        return self.test_id(f"csr-search-status-{option.filter_test_id}")

    def select_status(self, option: StatusOption) -> None:
        self.status_option(option).click()

    # Search.

    @property
    def search_box(self) -> Locator:
        return self.test_id("csr-search-query")

    def search_for(self, term: str) -> None:
        self.search_box.fill(term)

    def clear_search(self) -> None:
        self.search_box.fill("")

    # Summary cards.

    #: Summary card count test id -> the card's label.
    SUMMARY_LABELS = {
        "total": "All applications",
        "draft": "In progress",
        "submitted": "Submitted",
        "enrolled": "Enrolled",
        "rejected": "Rejected",
        "expired": "Expired",
        "review": "Awaiting review",
    }

    def summary_count(self, key: str) -> Locator:
        """The number on the summary card `key` ("total", "draft", ...)."""
        return self.test_id(f"summary-{key}")

    def summary_card(self, key: str) -> Locator:
        """The whole summary card (label + description + count)."""
        if key == "review":
            return self.test_id("summary-review-link")
        return self.summary_count(key).locator("xpath=ancestor::div[1]")

    # Applications table.

    #: Columns the list must show.
    REQUIRED_COLUMNS = (
        "Applicant",
        "SSN",
        "Channel",
        "Status",
        "Identity",
        "Eligibility",
        "Updated",
    )

    @property
    def rows(self) -> Locator:
        """The applications currently listed."""
        return self.table.locator("tbody tr")

    def row(self, text: str) -> Locator:
        """Rows whose visible text contains `text` (applicant name, member id...)."""
        return self.rows.filter(has_text=text)

    def row_by_identity(self, identity: str) -> Locator:
        """The listed application whose unique row test id is `identity`.

        Identities come from row_identity() and stay the same whatever the
        status filter or the search shows, unlike the applicant names, which
        several applications share.
        """
        return self.rows.filter(has=self.test_id(identity))

    def applicant_name(self, row: Locator) -> Locator:
        return row.locator('[data-testid^="member-draft-"]').first

    def member_number(self, row: Locator) -> Locator:
        """The member number the row shows. Draft rows display none."""
        return row.locator('[data-testid^="member-number-"]').first

    def row_identity(self, row: Locator) -> str:
        """The row's own unique application test id ("member-draft-<id>").

        Every row carries it on its application link's test id, drafts and
        non-drafts alike, so it is the row's identity across filters.
        """
        return row.locator('[data-testid^="member-draft-"]').first.get_attribute("data-testid")

    def row_status(self, row: Locator) -> Locator:
        """The status badge in the row's Status column."""
        return row.locator("td").nth(3).locator('[data-slot="badge"]').first

    def ssn_cell(self, row: Locator) -> Locator:
        return row.locator("td").nth(1)

    def applicant_entries(self) -> list[tuple[str, str]]:
        """As (applicant name, row identity) for every listed application."""
        entries = []
        for row in self.rows.all():
            entries.append((self.applicant_name(row).inner_text(), self.row_identity(row)))
        return entries

    def column_header(self, name: str) -> Locator:
        """The table's header cell labelled with the column `name`."""
        return self.table.locator("thead th, thead td").filter(has_text=name)

    # Pager.

    @property
    def pager_page(self) -> Locator:
        return self.test_id("applications-pager-page")

    @property
    def pager_range(self) -> Locator:
        return self.test_id("applications-pager-range")

    @property
    def previous_page(self) -> Locator:
        return self.test_id("applications-pager-previous")

    @property
    def next_page(self) -> Locator:
        return self.test_id("applications-pager-next")

    @property
    def nav(self) -> SideNav:
        return SideNav(self.page)
