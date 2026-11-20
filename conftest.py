"""Fixtures every test can use.

- `page` (from pytest-playwright) opens on the app's base URL, signed out.
- `staff_page` is a page already signed in as the staff user. Signing in is
  slow, so it happens once per test session and each test reuses the saved
  session (storage state) in a fresh browser context.
- `applications` is the Applications page on a signed-in `staff_page`.
"""

import pytest
from playwright.sync_api import Browser, Page, expect

from pages.applications_page import ApplicationsPage
from pages.login_page import LoginPage
from support import config

expect.set_options(timeout=config.DEFAULT_TIMEOUT_MS)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "base_url": config.BASE_URL, "viewport": {"width": 1440, "height": 900}}


@pytest.fixture
def context(context):
    """pytest-playwright's per-test context, with the suite's default timeout."""
    context.set_default_timeout(config.DEFAULT_TIMEOUT_MS)
    return context


@pytest.fixture(scope="session")
def staff_session(browser: Browser, browser_context_args) -> dict:
    """The staff user's signed-in session, saved once."""
    context = browser.new_context(**browser_context_args)
    try:
        page = context.new_page()
        page.set_default_timeout(config.DEFAULT_TIMEOUT_MS)
        LoginPage(page).open().sign_in_as_staff()
        return context.storage_state()
    finally:
        context.close()


@pytest.fixture
def staff_page(browser: Browser, browser_context_args, staff_session) -> Page:
    context = browser.new_context(**browser_context_args, storage_state=staff_session)
    page = context.new_page()
    page.set_default_timeout(config.DEFAULT_TIMEOUT_MS)
    yield page
    context.close()


@pytest.fixture
def applications(staff_page: Page) -> ApplicationsPage:
    return ApplicationsPage(staff_page).open()
