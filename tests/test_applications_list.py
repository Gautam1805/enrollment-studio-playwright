"""The Applications list: table columns, status filter, search, summary
counts, SSN masking and pagination."""

import math
import re

import pytest
from playwright.sync_api import expect

from pages.applications_page import ApplicationsPage, StatusOption

PER_PAGE = ApplicationsPage.PER_PAGE

#: An SSN cell shows only the last four digits.
MASKED_SSN = re.compile(r"^\*\*\*-\*\*-\d{4}$")
#: A real, unmasked SSN: three digits, two digits, four digits.
FULL_SSN = re.compile(r"\d{3}-\d{2}-\d{4}")


def _filter_by_status(applications: ApplicationsPage, option: StatusOption) -> int:
    """Select a status filter, wait for the list to settle and check it.

    Returns the summary count for the chosen status, so tests can compare it
    with the list. For "All" the list keeps showing every status, so the rows
    are only checked to appear.
    """
    count = int(applications.summary_count(option.summary_key).inner_text())
    applications.select_status(option)
    expect(applications.status_option(option)).to_have_attribute("aria-checked", "true")
    if count:
        expect(applications.rows).to_have_count(count if count < PER_PAGE else PER_PAGE)
        if option is not StatusOption.ALL:
            for row in applications.rows.all():
                expect(applications.row_status(row)).to_have_text(option.badge)
            expect(applications.pager_range).to_contain_text(f"of {count} matching applications")
    else:
        expect(applications.rows).to_have_count(0)
        expect(applications.pager_range).to_have_count(0)
    return count


def name_parts(full_name: str) -> tuple[str, str]:
    """Split "Marla Diaz" into ("Marla", "Diaz")."""
    parts = full_name.split()
    return parts[0], parts[-1]


def _rarest_target(entries: list[tuple[str, str]]) -> tuple[str, str]:
    """The application whose name parts are least shared with the others."""
    counts: dict[str, int] = {}
    for name, _ in entries:
        first, last = name_parts(name)
        counts[first] = counts.get(first, 0) + 1
        counts[last] = counts.get(last, 0) + 1
    return min(entries, key=lambda entry: sum(counts[part] for part in name_parts(entry[0])))


def _different_row(entries: list[tuple[str, str]], target: tuple[str, str]) -> tuple[str, str]:
    """A listed application none of the target's own name terms match."""
    terms = [term.lower() for term in name_parts(target[0])]
    for name, identity in entries:
        lower = name.lower()
        if all(term not in lower for term in terms) and identity != target[1]:
            return name, identity
    raise AssertionError(f"no second application clear of the target {target[0]!r}")


def test_list_table_shows_the_required_columns(applications: ApplicationsPage):
    """TC draft-1: the table has the Applicant, SSN, Channel, Status, Identity,
    Eligibility and Updated columns and shows application rows."""
    for name in applications.REQUIRED_COLUMNS:
        expect(applications.column_header(name)).to_be_visible()

    expect(applications.rows.first).to_be_visible()


def test_status_filter_starts_with_all_selected(applications: ApplicationsPage):
    """TC draft-2: All, In progress, Submitted, Enrolled, Rejected and Expired
    are offered, and "All" is selected by default so the list is unfiltered."""
    for option in applications.STATUS_OPTIONS:
        expect(applications.status_option(option)).to_be_visible()
        expect(applications.status_option(option)).to_have_text(option.label)

    expect(applications.status_option(StatusOption.ALL)).to_have_attribute("aria-checked", "true")
    for option in applications.STATUS_OPTIONS[1:]:
        expect(applications.status_option(option)).to_have_attribute("aria-checked", "false")

    total = int(applications.total.inner_text())
    unfiltered = re.compile(rf"of {total} (matching )?applications")
    expect(applications.pager_range).to_contain_text(unfiltered)
    expect(applications.rows).not_to_have_count(0)


def test_choosing_a_status_lists_only_that_status(applications: ApplicationsPage):
    """TC draft-3: "In progress" lists only drafts and "Enrolled" only enrolled
    applications; the other status is never listed."""
    _filter_by_status(applications, StatusOption.IN_PROGRESS)
    draft = applications.row_identity(applications.rows.first)

    _filter_by_status(applications, StatusOption.ENROLLED)
    enrolled = applications.row_identity(applications.rows.first)

    _filter_by_status(applications, StatusOption.IN_PROGRESS)
    expect(applications.row_by_identity(enrolled)).to_have_count(0)
    expect(applications.row_by_identity(draft)).to_have_count(1)

    _filter_by_status(applications, StatusOption.ENROLLED)
    expect(applications.row_by_identity(draft)).to_have_count(0)
    expect(applications.row_by_identity(enrolled)).to_have_count(1)


def test_search_narrows_to_matching_applications(applications: ApplicationsPage):
    """TC draft-4: searching by first name, last name or member number lists
    only the matching applications and hides the rest; clearing the search
    restores the complete list."""
    _filter_by_status(applications, StatusOption.ALL)
    entries = applications.applicant_entries()
    target_name, target_identity = _rarest_target(entries)
    _, other_identity = _different_row(entries, (target_name, target_identity))
    target_first, target_last = name_parts(target_name)
    full_page = len(entries)

    applications.search_for(target_first)
    expect(applications.row_by_identity(other_identity)).to_have_count(0)
    expect(applications.row_by_identity(target_identity)).to_have_count(1)
    for name, _ in applications.applicant_entries():
        assert target_first.lower() in name.lower(), f"{name} does not match {target_first!r}"

    applications.clear_search()
    expect(applications.rows).to_have_count(full_page)

    applications.search_for(target_last)
    expect(applications.row_by_identity(other_identity)).to_have_count(0)
    expect(applications.row_by_identity(target_identity)).to_have_count(1)
    for name, _ in applications.applicant_entries():
        assert target_last.lower() in name.lower(), f"{name} does not match {target_last!r}"

    applications.clear_search()
    expect(applications.rows).to_have_count(full_page)

    # By member number: draft rows display none, so take the number the list
    # itself shows for one enrolled application and search for that.
    _filter_by_status(applications, StatusOption.ENROLLED)
    shown = applications.rows.first
    member_number = applications.member_number(shown).inner_text()
    member_name = applications.applicant_name(shown).inner_text()
    member_identity = applications.row_identity(shown)

    _filter_by_status(applications, StatusOption.ALL)
    applications.search_for(member_number)
    expect(applications.rows).to_have_count(1)
    expect(applications.row_by_identity(member_identity)).to_have_count(1)
    expect(applications.applicant_name(applications.rows.first)).to_have_text(member_name)


def test_search_and_status_filter_combine(applications: ApplicationsPage):
    """TC draft-5: with the status filter on "In progress", the search only
    keeps applications whose name matches too; clearing the search restores
    the filtered list."""
    _filter_by_status(applications, StatusOption.IN_PROGRESS)
    drafts = applications.applicant_entries()
    _filter_by_status(applications, StatusOption.ENROLLED)
    enrolled = applications.applicant_entries()

    # The surname of an enrolled application that drafts share too, so the
    # search result would differ between statuses.
    draft_surnames = {name_parts(name)[1] for name, _ in drafts}
    mixed = [(name, identity) for name, identity in enrolled if name_parts(name)[1] in draft_surnames]
    if mixed:
        surname, non_draft = name_parts(mixed[0][0])[1], mixed[0][1]
    else:
        surname, non_draft = name_parts(drafts[0][0])[1], None

    draft_count = _filter_by_status(applications, StatusOption.IN_PROGRESS)
    draft = next(identity for name, identity in drafts if name_parts(name)[1] == surname)
    # A draft the search term must not list: it only leaves the list once the
    # search has applied, so waiting for its disappearance settles the search.
    unmatched = next(
        (identity for name, identity in drafts if surname.lower() not in name.lower()), None
    )

    applications.search_for(surname)
    if unmatched:
        expect(applications.row_by_identity(unmatched)).to_have_count(0)
    expect(applications.row_by_identity(draft)).to_have_count(1)
    for name, _ in applications.applicant_entries():
        assert surname.lower() in name.lower(), f"{name} does not match {surname!r}"
    for row in applications.rows.all():
        expect(applications.row_status(row)).to_have_text(StatusOption.IN_PROGRESS.badge)
    if non_draft:
        expect(applications.row_by_identity(non_draft)).to_have_count(0)

    applications.clear_search()
    if unmatched:
        expect(applications.row_by_identity(unmatched)).to_have_count(1)
    expect(applications.rows).to_have_count(draft_count if draft_count < PER_PAGE else PER_PAGE)


def test_summary_shows_every_category_with_its_count(applications: ApplicationsPage):
    """TC draft-6: the summary counts All applications, In progress, Submitted,
    Enrolled, Rejected, Expired and Awaiting review."""
    for key, label in applications.SUMMARY_LABELS.items():
        expect(applications.summary_card(key)).to_contain_text(label)
        expect(applications.summary_count(key)).to_have_text(re.compile(r"^\d+$"))


def test_summary_counts_match_each_filtered_list(applications: ApplicationsPage):
    """TC draft-7: for every status the number of listed and of matching
    applications equals the status's summary count, and "All" matches the All
    applications count."""
    total = int(applications.total.inner_text())
    for option in applications.STATUS_OPTIONS:
        count = _filter_by_status(applications, option)
        if option is StatusOption.ALL:
            assert count == total, f"All applications count is {count}, total {total}"

    _filter_by_status(applications, StatusOption.ALL)


def test_ssns_are_masked_to_the_last_four_digits(applications: ApplicationsPage):
    """TC draft-8: every SSN cell shows ***-**-XXXX only, and no full SSN is
    visible anywhere in the list."""
    expect(applications.rows.first).to_be_visible()
    for row in applications.rows.all():
        expect(applications.ssn_cell(row)).to_have_text(MASKED_SSN)

    expect(applications.table).not_to_contain_text(FULL_SSN)


def _page_range_text(start: int, end: int, total: int) -> re.Pattern:
    """The pager's "26–50 of 83 applications" text for a page slice."""
    return re.compile(rf"{start}[–-]{end} of {total} applications")


def test_pagination_shows_25_per_page_and_moves_between_pages(applications: ApplicationsPage):
    """TC draft-9: the All list shows 25 applications per page with "Page X of
    Y", and Next and Previous move one page at a time."""
    _filter_by_status(applications, StatusOption.ALL)
    total = int(applications.total.inner_text())
    pages = math.ceil(total / PER_PAGE)
    if pages < 2:
        pytest.skip("the All list must span more than one page of 25")

    expect(applications.pager_page).to_have_text(f"Page 1 of {pages}")
    expect(applications.rows).to_have_count(PER_PAGE)
    expect(applications.pager_range).to_contain_text(_page_range_text(1, PER_PAGE, total))
    expect(applications.previous_page).to_be_disabled()

    applications.next_page.click()
    expect(applications.pager_page).to_have_text(f"Page 2 of {pages}")
    expect(applications.pager_range).to_contain_text(
        _page_range_text(PER_PAGE + 1, min(2 * PER_PAGE, total), total)
    )
    expect(applications.rows).to_have_count(min(PER_PAGE, total - PER_PAGE))
    expect(applications.previous_page).to_be_enabled()

    applications.previous_page.click()
    expect(applications.pager_page).to_have_text(f"Page 1 of {pages}")
    expect(applications.rows).to_have_count(PER_PAGE)

    # Forward through every page: together they cover all applications.
    for _ in range(pages - 1):
        applications.next_page.click()
    expect(applications.pager_page).to_have_text(f"Page {pages} of {pages}")
    expect(applications.rows).to_have_count(total - PER_PAGE * (pages - 1))
    expect(applications.next_page).to_be_disabled()
    expect(applications.previous_page).to_be_enabled()
