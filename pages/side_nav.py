"""The sidebar shown on every signed-in page."""

from enum import Enum

from pages.base_page import BasePage


class NavItem(Enum):
    """Sidebar entries: the data-testid and the path each one opens."""

    APPLICATIONS = ("nav-applications", "/")
    REVIEW_QUEUE = ("nav-review-queue", "/review-queue")
    POSSIBLE_DUPLICATES = ("nav-duplicates", "/duplicates")
    AUDIT_LOG = ("nav-audit-log", "/audit-log")
    DELETION_REQUESTS = ("nav-deletion-requests", "/deletion-requests")
    STAFF_ACCESS = ("nav-staff", "/staff")

    @property
    def test_id(self) -> str:
        return self.value[0]

    @property
    def path(self) -> str:
        return self.value[1]


class SideNav(BasePage):
    @property
    def signed_in_email(self):
        return self.test_id("session-email")

    @property
    def new_enrollment(self):
        return self.test_id("member-new")

    def open(self, item: NavItem) -> None:
        self.test_id(item.test_id).click()
        self.wait_for_path(item.path)

    def start_new_enrollment(self) -> None:
        self.new_enrollment.click()

    def sign_out(self):
        from pages.login_page import LoginPage  # the two pages lead to each other

        self.test_id("sign-out").click()
        return LoginPage(self.page).wait_until_shown()
