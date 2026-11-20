"""Sign-in and sign-out. Each test starts signed out (pytest-playwright's
`page` is a fresh browser context)."""

import pytest
from playwright.sync_api import Page, expect

from pages.login_page import LoginPage
from support import config


@pytest.mark.smoke
def test_sign_in_page_shows_help_links(page: Page):
    """The sign-in page offers first-time sign-in and password reset."""
    login = LoginPage(page).open()

    expect(login.email).to_be_visible()
    expect(login.password).to_be_visible()
    expect(login.first_time_link).to_be_visible()
    expect(login.forgot_password_link).to_be_visible()


def test_protected_page_redirects_to_sign_in(page: Page):
    """Signed-out visitors are sent to sign in."""
    page.goto("/review-queue")

    LoginPage(page).wait_until_shown()


@pytest.mark.smoke
def test_staff_can_sign_in_and_out(page: Page):
    """Staff sign in, land on Applications signed in as themselves, and can sign out."""
    applications = LoginPage(page).open().sign_in_as_staff()

    expect(applications.heading).to_have_text("Applications")
    expect(applications.table).to_be_visible()
    expect(applications.nav.signed_in_email).to_have_text(config.username(), ignore_case=True)

    login = applications.nav.sign_out()

    expect(login.email).to_be_visible()
