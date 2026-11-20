"""The sign-in page."""

from playwright.sync_api import expect

from pages.applications_page import ApplicationsPage
from pages.base_page import BasePage
from support import config


class LoginPage(BasePage):
    PATH = "/login"

    @property
    def email(self):
        return self.test_id("login-email")

    @property
    def password(self):
        return self.test_id("login-password")

    @property
    def submit(self):
        return self.test_id("login-submit")

    @property
    def first_time_link(self):
        return self.test_id("login-first-time")

    @property
    def forgot_password_link(self):
        return self.test_id("login-forgot-password")

    def open(self) -> "LoginPage":
        self.page.goto(self.PATH)
        return self.wait_until_shown()

    def wait_until_shown(self) -> "LoginPage":
        self.wait_for_path(self.PATH)
        expect(self.email).to_be_visible()
        return self

    def sign_in(self, email: str, password: str) -> ApplicationsPage:
        self.email.fill(email)
        self.password.fill(password)
        self.submit.click()
        self.wait_for_path(ApplicationsPage.PATH, timeout=config.SIGN_IN_TIMEOUT_MS)
        return ApplicationsPage(self.page).wait_until_loaded()

    def sign_in_as_staff(self) -> ApplicationsPage:
        return self.sign_in(config.username(), config.password())
