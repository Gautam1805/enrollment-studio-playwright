"""TC 149-156: the Applications list's columns, status filters, search,
summary counts, masked SSNs and pagination.

Tests pick their data live: `ApplicationList` scans the same list the page
loads, so names and counts come from the run instead of being hard-coded.
"""

import math
import re
from typing import Callable
from urllib.parse import quote

import pytest
from playwright.sync_api import APIRequestContext, Locator, expect

from pages.applications_page import ApplicationsPage, Status

#: The list shows every SSN masked to its last 4 digits, as ***-**-1234.
MASKED_SSN = re.compile(r"^\*\*\*-\*\*-\d{4}$")

PER_PAGE = 25


class ApplicationList:
    """The data the Applications list itself loads, via the app's list API.

    Test data is chosen here, not hard-coded: names, member numbers and
    status counts must fit whatever the environment happens to be seeded
    with. `app_searches` asks the app's own search endpoint the way the
    page calls it (its limit accepts at most 100), so a term is only
    offered when its results are pure name matches small enough to check
    row by row.
    """

    PAGE_SIZE = 100
    MAX_RESULTS = 24  # comfortably below one page of the list

    def __init__(self, request: APIRequestContext):
        self.request = request
        rows: list[dict] = []
        offset = 0
        while True:
            batch = self._get(f"/api/members?limit={self.PAGE_SIZE}&offset={offset}")
            rows.extend(batch)
            if len(batch) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE
        self.rows = rows
        self._page_one_cache: dict[str | None, list[dict]] = {}

    def _get(self, url: str) -> list[dict]:
        """GET `url` and return its array of row dicts. Anything else is an
        error payload, not data: e.g. the search endpoint answers 422 with
        {'detail': [...]} when a limit goes over its cap of 100."""
        response = self.request.get(url)
        if not response.ok:
            raise AssertionError(f"GET {url} failed with status {response.status}: {response.text()[:300]}")
        body = response.json()
        if not isinstance(body, list):
            raise AssertionError(f"GET {url} returned a {type(body).__name__}, not a row list: {body}")
        return body

    @property
    def total(self) -> int:
        return len(self.rows)

    def count_in_status(self, status: str) -> int:
        """Applications the environment has in `status`, e.g. 'DRAFT'."""
        return sum(1 for row in self.rows if row["status"] == status)

    @staticmethod
    def name_of(row: dict) -> str:
        return f"{row['first_name']} {row['last_name']}"

    def app_searches(self, term: str) -> list[dict]:
        """Everything the app's search returns for `term` (rows it shows).
        The endpoint accepts a limit of at most 100, the cap the page's own
        calls stay under."""
        return self._get(f"/api/csr/search?limit={self.PAGE_SIZE}&offset=0&query={quote(term)}")

    def _page_one(self, status: str | None) -> list[dict]:
        """Page 1 of one list view, fetched exactly as the UI fetches it:
        `status` None for the unfiltered 'All' list, otherwise the view a
        status chip produces ('DRAFT' is what In progress filters by)."""
        if status not in self._page_one_cache:
            if status is None:
                url = f"/api/members?limit={PER_PAGE}&offset=0"
            else:
                url = f"/api/csr/search?limit={PER_PAGE}&offset=0&status={status}"
            self._page_one_cache[status] = self._get(url)
        return self._page_one_cache[status]

    def _on_page_one(self, term: str, views: tuple[str | None, ...]) -> bool:
        """Some row belonging to `term` shows on page 1 of every view."""
        return all(
            any(self.name_matches(row, term) for row in self._page_one(view)) for view in views
        )

    @staticmethod
    def name_matches(row: dict, term: str) -> bool:
        needle = term.casefold()
        return needle in row["first_name"].casefold() or needle in row["last_name"].casefold()

    def _pick(self, candidates, *, statuses: tuple[str, ...] = (), only_status: str | None = None,
              applicants: int = 1, on_first_page: tuple[str | None, ...] = (),
              matches: Callable[[dict, str], bool] | None = None) -> tuple[str, list[dict]]:
        """The first candidate the app's search agrees to: at most MAX_RESULTS
        rows, all belonging to the term, covering every wanted status
        (`statuses`), all in one status (`only_status`), at least
        `applicants` distinct applicants, and — when `on_first_page` lists
        views (None = the 'All' list) — a matching row on page 1 of every
        one of them, the place page-1-only assertions read from."""
        belongs = matches or self.name_matches
        for term in candidates:
            found = self.app_searches(term)
            if not 1 <= len(found) <= self.MAX_RESULTS:
                continue
            statuses_found = {row["status"] for row in found}
            if not statuses_found >= set(statuses):
                continue
            if only_status and statuses_found != {only_status}:
                continue
            if len({self.name_of(row) for row in found}) < applicants:
                continue
            own = [row for row in self.rows if belongs(row, term)]
            if len(own) != len(found):
                continue  # the app matched something besides applicants' names
            if on_first_page and not self._on_page_one(term, on_first_page):
                continue  # page 1 of a wanted view would not show the term
            return term, found
        raise AssertionError(f"no searched term fits the request (wanted statuses {statuses or 'any'}); is the seeded list still there?")

    def pick_first_name(self, *, statuses: tuple[str, ...] = (), only_status: str | None = None,
                        on_first_page: tuple[str | None, ...] = ()) -> tuple[str, list[dict]]:
        """A first name the list knows: the term and its matching rows.
        With `on_first_page`, a matching row must also sit on page 1 of
        every listed view (None = 'All'), as page-1-only assertions need."""
        candidates = sorted({row["first_name"] for row in self.rows})
        return self._pick(candidates, statuses=statuses, only_status=only_status, on_first_page=on_first_page)

    def pick_last_name(self, *, applicants: int = 2) -> tuple[str, list[dict]]:
        """A last name several applicants share: the term and its rows."""
        candidates = sorted({row["last_name"] for row in self.rows})
        return self._pick(candidates, applicants=applicants)

    def pick_member_number(self) -> tuple[str, list[dict]]:
        """A member number exactly one application carries."""
        candidates = sorted({row["member_number"] for row in self.rows if row["member_number"]})
        return self._pick(candidates, matches=lambda row, term: bool(row["member_number"]) and row["member_number"] == term)

    def other_name(self, term: str, matched: list[dict]) -> str:
        """An applicant the search for `term` leaves out. Neither the
        matched rows nor their displayed e-mail addresses mention it, so
        an assertion that it is gone is sound."""
        matched_text = " ".join(
            f"{row['first_name']} {row['last_name']} {row.get('email', '')}" for row in matched
        ).casefold()
        for row in sorted(self.rows, key=self.name_of):
            name = self.name_of(row)
            if self.name_matches(row, term) or name.casefold() in matched_text:
                continue
            return name
        raise AssertionError(f"no applicant besides '{term}' in the seeded list")


@pytest.fixture
def application_list(applications: ApplicationsPage) -> ApplicationList:
    """The list's data, read once per test with the session's credentials."""
    return ApplicationList(applications.page.request)


def assert_rows_shown(applications: ApplicationsPage, count: int) -> None:
    """The list shows exactly `count` rows after UI actions have settled."""
    expect(applications.rows).to_have_count(min(count, PER_PAGE))


def assert_status_badge(applications: ApplicationsPage, row: Locator, badge: str) -> None:
    """`row`'s status badge reads `badge`."""
    expect(applications.row_status(row)).to_have_text(badge)


def test_list_columns_and_default_filter(applications: ApplicationsPage):
    """TC 149: Columns and 'All' filter are shown before anything is clicked."""
    for column in ("Applicant", "SSN", "Channel", "Status", "Identity", "Eligibility", "Updated"):
        expect(applications.column_header(column)).to_be_visible()

    for status in Status:
        expect(applications.status_filter(status)).to_be_visible()
        expect(applications.status_filter(status)).to_have_text(status.label)
    expect(applications.status_filter(Status.ALL)).to_have_attribute("aria-checked", "true")
    expect(applications.status_filter(Status.SUBMITTED)).to_have_attribute("aria-checked", "false")

    # No click has happened: the list is already on the unfiltered view.
    expect(applications.search).to_have_value("")
    expect(applications.rows.first).to_be_visible()
    expect(applications.result_range).not_to_contain_text("matching")


def test_status_filter_shows_only_that_status(applications: ApplicationsPage, application_list: ApplicationList):
    """TC 150: A status chip shows only applications in that status."""
    draft_term, _ = application_list.pick_first_name(only_status="DRAFT", on_first_page=(None, "DRAFT"))
    enrolled_term, _ = application_list.pick_first_name(statuses=("ENROLLED",))

    expect(applications.rows.first).to_be_visible()  # the list has rendered
    statuses = set()
    for index in range(applications.rows.count()):
        statuses.add(applications.row_status(applications.rows.nth(index)).text_content())
    assert statuses & {"Draft", "Submitted", "Enrolled", "Rejected", "Expired"}, f"the unfiltered list shows one status only: {statuses}"

    applications.filter_by_status(Status.IN_PROGRESS)
    assert_rows_shown(applications, application_list.count_in_status("DRAFT"))
    for index in range(applications.rows.count()):
        assert_status_badge(applications, applications.rows.nth(index), "Draft")
    expect(applications.row_for(draft_term).first).to_be_visible()

    applications.filter_by_status(Status.ENROLLED)
    assert_rows_shown(applications, application_list.count_in_status("ENROLLED"))
    for index in range(applications.rows.count()):
        assert_status_badge(applications, applications.rows.nth(index), "Enrolled")
    expect(applications.row_for(enrolled_term).first).to_be_visible()
    expect(applications.row_for(draft_term)).to_have_count(0)

    applications.filter_by_status(Status.ALL)
    assert_rows_shown(applications, application_list.total)
    statuses = {applications.row_status(applications.rows.nth(index)).text_content() for index in range(applications.rows.count())}
    assert len(statuses) > 1, "after 'All' the list shows one status only"
    expect(applications.row_for(draft_term).first).to_be_visible()
    # The enrolled seeds are older than the list's first page; page forward to it.
    applications.show_row(enrolled_term)
    expect(applications.row_for(enrolled_term).first).to_be_visible()


def test_summary_counts_match_the_filtered_lists(applications: ApplicationsPage):
    """TC 154: Every summary card's count matches the list it stands for."""
    for label in ("All applications", "In progress", "Submitted", "Enrolled", "Rejected", "Expired", "Awaiting review"):
        expect(applications.summary_label(label)).to_be_visible()
    expect(applications.awaiting_review_count).to_have_text(re.compile(r"^\d+$"))

    for status in Status:
        applications.filter_by_status(status)
        summary = applications.summary_count(status).inner_text()
        assert summary.isdigit(), f"the {status.label} card shows '{summary}' instead of a count"
        # Let the list settle on the filtered view before reading its pager.
        expect(applications.rows).to_have_count(min(int(summary), PER_PAGE))
        applications_count = applications.result_count()
        assert applications_count == int(summary), f"the {status.label} card says {summary} but the list holds {applications_count}"
        if summary == "0":
            expect(applications.empty_state).to_be_visible()
        else:
            expect(applications.result_range).to_contain_text(f"of {summary}")


def test_ssns_are_masked_to_last_4_digits(applications: ApplicationsPage, application_list: ApplicationList):
    """TC 155: SSNs show as ***-**-1234, only the last 4 digits visible."""
    term, matched = application_list.pick_first_name()
    applications.set_search(term)  # narrow first: the term's row need not sit on page 1 unfiltered
    expect(applications.rows).to_have_count(len(matched))  # every matching row is on screen now
    expect(applications.row_ssn(applications.row_for(term).first)).to_have_text(MASKED_SSN)

    applications.clear_search()
    expect(applications.rows).to_have_count(PER_PAGE)  # page one of 'All' is fully rendered
    for index in range(applications.rows.count()):
        expect(applications.row_ssn(applications.rows.nth(index))).to_have_text(MASKED_SSN)


def test_pagination_25_per_page_with_previous_and_next(applications: ApplicationsPage, application_list: ApplicationList):
    """TC 156: 25 applications per page, 'Page X of Y', Previous and Next."""
    total = application_list.total
    assert total > PER_PAGE, f"two pages need more than {PER_PAGE} applications; the seeded list has {total}"
    pages = math.ceil(total / PER_PAGE)

    expect(applications.rows).to_have_count(PER_PAGE)
    expect(applications.pager_page).to_have_text(f"Page 1 of {pages}")
    expect(applications.result_range).to_contain_text(f"of {total}")
    expect(applications.pager_previous).to_be_disabled()
    first_page_application = applications.row_link(applications.rows.first).get_attribute("href")

    applications.go_next()
    expect(applications.pager_page).to_have_text(f"Page 2 of {pages}")
    expect(applications.result_range).to_contain_text(f"of {total}")
    expect(applications.rows).to_have_count(min(PER_PAGE, total - PER_PAGE))
    expect(applications.pager_previous).to_be_enabled()
    assert applications.row_link(applications.rows.first).get_attribute("href") != first_page_application, "Next did not move the list: page 2 opens with the same application"

    applications.go_previous()
    expect(applications.pager_page).to_have_text(f"Page 1 of {pages}")
    expect(applications.rows).to_have_count(PER_PAGE)
    expect(applications.row_link(applications.rows.first)).to_have_attribute("href", first_page_application)


def test_search_narrows_by_first_name_last_name_and_member_number(applications: ApplicationsPage, application_list: ApplicationList):
    """TC 151: Searching by first name, last name or member number narrows the list."""
    unfiltered_total = application_list.total

    first_term, first_found = application_list.pick_first_name()
    applications.set_search(first_term)
    expect(applications.rows).to_have_count(len(first_found))
    expect(applications.rows.filter(has_text=first_term)).to_have_count(len(first_found))
    expect(applications.row_for(application_list.other_name(first_term, first_found))).to_have_count(0)

    applications.clear_search()
    expect(applications.rows).to_have_count(min(unfiltered_total, PER_PAGE))

    last_term, last_found = application_list.pick_last_name()
    applications.set_search(last_term)
    expect(applications.rows).to_have_count(len(last_found))
    expect(applications.rows.filter(has_text=last_term)).to_have_count(len(last_found))
    expect(applications.row_for(application_list.other_name(last_term, last_found))).to_have_count(0)

    applications.clear_search()
    expect(applications.rows).to_have_count(min(unfiltered_total, PER_PAGE))

    member_number, member_found = application_list.pick_member_number()
    applications.set_search(member_number)
    expect(applications.rows).to_have_count(len(member_found))
    expect(applications.rows.filter(has_text=member_number)).to_have_count(len(member_found))
    expect(applications.row_for(application_list.other_name(member_number, member_found))).to_have_count(0)


def test_search_without_matches_shows_empty_list(applications: ApplicationsPage, application_list: ApplicationList):
    """TC 152: A search term nothing matches empties the list."""
    assert application_list.total >= 1, "the environment's list should hold at least one application"
    assert application_list.app_searches("AUTO-Nomatch") == [], "'AUTO-Nomatch' should be a term nothing matches"

    applications.set_search("AUTO-Nomatch")

    expect(applications.empty_state).to_be_visible()
    expect(applications.rows).to_have_count(0)


def test_search_and_status_filter_work_together(applications: ApplicationsPage, application_list: ApplicationList):
    """TC 153: With a search active the status filter still narrows further."""
    term, matching = application_list.pick_first_name(statuses=("DRAFT", "SUBMITTED"))
    draft_rows = [row for row in matching if row["status"] == "DRAFT"]
    submitted_rows = [row for row in matching if row["status"] == "SUBMITTED"]

    applications.set_search(term)
    expect(applications.rows).to_have_count(len(matching))
    statuses = {applications.row_status(applications.rows.nth(index)).text_content() for index in range(applications.rows.count())}
    assert statuses >= {"Draft", "Submitted"}, f"searching '{term}' did not show statuses In progress and Submitted together: {statuses}"

    applications.filter_by_status(Status.SUBMITTED)
    expect(applications.rows).to_have_count(len(submitted_rows))
    expect(applications.rows.filter(has_text=term)).to_have_count(len(submitted_rows))
    for index in range(applications.rows.count()):
        assert_status_badge(applications, applications.rows.nth(index), "Submitted")

    applications.filter_by_status(Status.IN_PROGRESS)
    expect(applications.rows).to_have_count(len(draft_rows))
    expect(applications.rows.filter(has_text=term)).to_have_count(len(draft_rows))
    for index in range(applications.rows.count()):
        assert_status_badge(applications, applications.rows.nth(index), "Draft")
