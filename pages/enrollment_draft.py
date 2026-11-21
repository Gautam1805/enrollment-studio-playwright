"""A saved enrollment draft (/enroll/<draft id>/<step>) and how a new
enrollment is started.

`start_new_draft` expects a signed-in `page`: it opens the New enrollment
flow, fills the profile and saves it; the returned page object is then on
step 2 (Address) of the new draft.
"""

import re
from urllib.parse import urlparse

from playwright.sync_api import Page, expect

from pages.applications_page import ApplicationsPage
from pages.base_page import BasePage
from pages.enrollment_steps import (
    AddressStep,
    DependentsStep,
    DocumentsStep,
    PlanStep,
    ProfileStep,
    ReviewStep,
    VerificationStep,
)
from pages.side_nav import SideNav

#: step slug -> "Step N of 7"
STEPS = {"profile": 1, "address": 2, "verification": 3, "dependents": 4, "plan": 5, "documents": 6, "review": 7}

_DRAFT_ID_IN_URL = re.compile(r"/enroll/([0-9a-fA-F-]{36})")


class EnrollmentDraftPage(BasePage):
    """One draft and navigation between its steps."""

    def __init__(self, page: Page, draft_id: str) -> None:
        super().__init__(page)
        self.draft_id = draft_id

    @classmethod
    def from_url(cls, page: Page) -> "EnrollmentDraftPage":
        """Draft id taken from the page's /enroll/<id>/<step> URL."""
        match = _DRAFT_ID_IN_URL.search(page.url)
        if not match:
            raise AssertionError(f"no enrollment draft id in URL {page.url}")
        return cls(page, match.group(1))

    def base_path(self) -> str:
        return f"/enroll/{self.draft_id}"

    # ---- step page objects -------------------------------------------------
    @property
    def profile(self) -> ProfileStep:
        return ProfileStep(self.page)

    @property
    def address(self) -> AddressStep:
        return AddressStep(self.page)

    @property
    def verification(self) -> VerificationStep:
        return VerificationStep(self.page)

    @property
    def dependents(self) -> DependentsStep:
        return DependentsStep(self.page)

    @property
    def plan(self) -> PlanStep:
        return PlanStep(self.page)

    @property
    def documents(self) -> DocumentsStep:
        return DocumentsStep(self.page)

    @property
    def review(self) -> ReviewStep:
        return ReviewStep(self.page)

    def step(self, name: str):
        return getattr(self, name)

    # ---- navigation --------------------------------------------------------
    def current_step(self) -> str:
        """The step in the URL, or "" when not on a draft page."""
        path = urlparse(self.page.url).path.rstrip("/")
        tail = path.rsplit("/", 1)[-1]
        return tail if tail in STEPS else ""

    def open_step(self, name: str) -> "EnrollmentDraftPage":
        assert name in STEPS
        self.page.goto(f"{self.base_path()}/{name}")
        return self.wait_for_step(name)

    def wait_for_step(self, name: str) -> "EnrollmentDraftPage":
        """Wait until `/enroll/<id>/<step>` shows that step's UI."""
        assert name in STEPS
        self.wait_for_path(f"{self.base_path()}/{name}")
        expect(self.test_id("step-content")).to_be_visible()
        expect(self.page.locator("nav[aria-label='Enrollment steps']")).to_contain_text(
            f"Step {STEPS[name]} of 7"
        )
        return self

    def go_next(self) -> "EnrollmentDraftPage":
        """Follow the "Next:" link at the bottom of the current step."""
        link = self.test_id("step-next")
        expect(link).to_be_visible()
        link.click()
        return self


def start_new_draft(page: Page, profile_data: dict[str, str]) -> EnrollmentDraftPage:
    """Start a New enrollment, fill the profile and save it.

    Returns the draft page object on step 2 (Address), the step a saved
    profile opens.
    """
    if urlparse(page.url).path != ApplicationsPage.PATH:
        ApplicationsPage(page).open()  # the sidebar with "New enrollment" lives there
    SideNav(page).start_new_enrollment()
    page.wait_for_url("**/enroll/new/profile")
    form = ProfileStep(page)
    form.fill(profile_data)
    form.save()
    return EnrollmentDraftPage.from_url(page).wait_for_step("address")
