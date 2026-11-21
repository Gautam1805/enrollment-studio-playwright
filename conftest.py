"""Fixtures every test can use, and the test report's set-up.

- `page` (from pytest-playwright) opens on the app's base URL, signed out.
- `staff_page` is a page already signed in as the staff user. Signing in is
  slow, so it happens once per test session and each test reuses the saved
  session (storage state) in a fresh browser context.
- `applications` is the Applications page on a signed-in `staff_page`.

Report: pytest writes reports/report.html (see pytest.ini) with each test's
description (its docstring's first line) and, for a failed test, a
screenshot of the page at the moment it failed. Video and trace of failed
tests go to test-results/.
"""

import base64
import html

import pytest
import pytest_html
from playwright.sync_api import Browser, Page, expect
from pytest_metadata.plugin import metadata_key

from pages.applications_page import ApplicationsPage
from pages.login_page import LoginPage
from support import config as app_config

expect.set_options(timeout=app_config.DEFAULT_TIMEOUT_MS)


# ---- fixtures ---------------------------------------------------------------


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "base_url": app_config.BASE_URL, "viewport": {"width": 1440, "height": 900}}


@pytest.fixture
def context(context):
    """pytest-playwright's per-test context, with the suite's default timeout."""
    context.set_default_timeout(app_config.DEFAULT_TIMEOUT_MS)
    return context


@pytest.fixture(scope="session")
def staff_session(browser: Browser, browser_context_args) -> dict:
    """The staff user's signed-in session, saved once."""
    context = browser.new_context(**browser_context_args)
    try:
        page = context.new_page()
        page.set_default_timeout(app_config.DEFAULT_TIMEOUT_MS)
        LoginPage(page).open().sign_in_as_staff()
        return context.storage_state()
    finally:
        context.close()


@pytest.fixture
def staff_page(new_context, staff_session) -> Page:
    """A signed-in page. Made with pytest-playwright's new_context, so a
    failed test keeps its video and trace like any other."""
    context = new_context(storage_state=staff_session)
    context.set_default_timeout(app_config.DEFAULT_TIMEOUT_MS)
    return context.new_page()


@pytest.fixture
def applications(staff_page: Page) -> ApplicationsPage:
    return ApplicationsPage(staff_page).open()


# ---- the HTML report --------------------------------------------------------


def pytest_configure(config):
    config.stash[metadata_key]["Application"] = app_config.BASE_URL


def pytest_html_report_title(report):
    report.title = "Member Enrollment Studio: UI test report"


def pytest_html_results_table_header(cells):
    cells.insert(2, "<th>Description</th>")


def pytest_html_results_table_row(report, cells):
    cells.insert(2, f"<td>{html.escape(getattr(report, 'description', ''))}</td>")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    doc = getattr(item.function, "__doc__", None) or ""
    report.description = doc.strip().splitlines()[0] if doc.strip() else ""
    if report.when == "call" and report.failed:
        page = item.funcargs.get("staff_page") or item.funcargs.get("page")
        if page is not None and not page.is_closed():
            try:
                shot = base64.b64encode(page.screenshot(full_page=True)).decode()
            except Exception:  # a page that died cannot be photographed
                return
            report.extras = [*getattr(report, "extras", []), pytest_html.extras.png(shot, "Screen at failure")]
