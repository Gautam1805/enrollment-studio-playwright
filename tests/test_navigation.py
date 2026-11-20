"""The sidebar takes signed-in staff to each section."""

import pytest
from playwright.sync_api import expect

from pages.applications_page import ApplicationsPage
from pages.side_nav import NavItem


@pytest.mark.parametrize(
    ("item", "heading"),
    [
        (NavItem.REVIEW_QUEUE, "Review queue"),
        (NavItem.POSSIBLE_DUPLICATES, "Possible duplicates"),
        (NavItem.AUDIT_LOG, "Audit log"),
        (NavItem.DELETION_REQUESTS, "Deletion requests"),
        (NavItem.STAFF_ACCESS, "Staff access"),
    ],
    ids=lambda value: value.name.lower() if isinstance(value, NavItem) else None,
)
def test_sidebar_opens_page(applications: ApplicationsPage, item: NavItem, heading: str):
    """Each sidebar entry opens its page."""
    nav = applications.nav

    nav.open(item)

    assert nav.current_path() == item.path
    expect(nav.heading).to_have_text(heading)
