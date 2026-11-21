"""The seven steps of an enrollment (profile, address, ..., review).

Every step is a section of a signed-in draft under /enroll/<draft id>/...,
rendered inside the `step-content` container. Step objects expose locators
and actions (with the wait an action needs to finish); assertions live in
tests. The draft page that moves between steps lives in
pages/enrollment_draft.py.
"""

import re

from playwright.sync_api import Locator
from playwright.sync_api import expect

from pages.base_page import BasePage

#: A draft step URL such as /enroll/<draft id>/address. The id is required: an
#: unsaved draft lives on /enroll/new/<step>, so "new" must not match here or a
#: wait for the post-save URL would return before the app navigates at all.
DRAFT_STEP_URL = re.compile(r"/enroll/[0-9a-fA-F-]{36}/address/?$")


class EnrollStep(BasePage):
    """Plumbing shared by every wizard step."""

    @property
    def content(self) -> Locator:
        return self.test_id("step-content")

    @property
    def step_count(self) -> Locator:
        """The "Step N of 7" line in the step rail."""
        return self.page.locator("nav[aria-label='Enrollment steps'] p")

    def after_heading(self, heading: str) -> Locator:
        """The element right after an h3 heading inside step content."""
        return self.content.locator(f"xpath=//h3[normalize-space()='{heading}']/following-sibling::*[1]")

    def status_with(self, text: str) -> Locator:
        return self.content.locator("[role='status']").filter(has_text=text)


class ProfileStep(EnrollStep):
    """Step 1: the applicant's profile."""

    FIELDS = (
        ("first_name", "input-first-name"),
        ("last_name", "input-last-name"),
        ("date_of_birth", "input-date-of-birth"),
        ("ssn", "input-ssn-full-to-set-update"),
        ("email", "input-email"),
        ("phone", "input-phone"),
        ("address_line_1", "input-address-line-1"),
        ("address_line_2", "input-address-line-2"),
        ("city", "input-city"),
        ("state", "input-state"),
        ("zip_code", "input-zip-code"),
    )

    @property
    def heading(self) -> Locator:
        return self.content.get_by_role("heading", name="Applicant Profile")

    def fill(self, values: dict[str, str]) -> None:
        for name, testid in self.FIELDS:
            value = values.get(name)
            if value:
                self.test_id(testid).fill(value)

    def save(self) -> None:
        """Save and continue; a new draft opens step 2 (Address)."""
        self.test_id("member-save").click()
        self.page.wait_for_url(DRAFT_STEP_URL)


class AddressStep(EnrollStep):
    """Step 2: USPS validation of the residential address."""

    @property
    def validate(self) -> Locator:
        return self.test_id("address-validate")

    @property
    def override_reason(self) -> Locator:
        return self.test_id("address-override-reason")

    @property
    def keep_as_entered_button(self) -> Locator:
        return self.test_id("address-override-submit")

    @property
    def not_found_heading(self) -> Locator:
        return self.page.get_by_role("heading", name="Address not found")

    @property
    def keep_option(self) -> Locator:
        """The card offered when USPS cannot find the address."""
        return self.content.get_by_role("heading", name="Keep the address as entered")

    @property
    def saved_card(self) -> Locator:
        """The dl under the "Saved address" heading."""
        return self.after_heading("Saved address")

    @property
    def saved_address(self) -> Locator:
        return self.saved_card.locator("dd").first

    @property
    def saved_status(self) -> Locator:
        """The status badge dd ("Not verified", "Kept as entered (override)", ...)."""
        return self.saved_card.locator("dd").nth(1)

    @property
    def history(self) -> Locator:
        """Address history: "no changes" paragraph or the entries list.

        The entries list is a div[role="list"], whose entries are
        div[role="listitem"] (not a ul/li markup like the audit lists).
        """
        return self.after_heading("Address history")

    def history_entry(self, text: str) -> Locator:
        return self.history.get_by_role("listitem").filter(has_text=text)

    def keep_as_entered(self, reason: str) -> None:
        """Keep the address unvalidated, with the given reason."""
        self.override_reason.fill(reason)
        self.keep_as_entered_button.click()
        expect(self.saved_status).to_have_text("Kept as entered (override)")


class VerificationStep(EnrollStep):
    """Step 3: identity and eligibility checks."""

    @property
    def identity_run(self) -> Locator:
        return self.test_id("identity-check")

    @property
    def eligibility_run(self) -> Locator:
        return self.test_id("eligibility-check")

    @property
    def identity_status(self) -> Locator:
        return self.after_heading("Identity Status")

    @property
    def eligibility_status(self) -> Locator:
        return self.after_heading("Eligibility Status")

    @property
    def eligibility_code(self) -> Locator:
        return self.test_id("eligibility-code")

    @property
    def identity_audit(self) -> Locator:
        return self.after_heading("Identity Audit").locator("li")

    @property
    def eligibility_audit(self) -> Locator:
        return self.after_heading("Eligibility Audit").locator("li")

    def run_identity_check(self) -> None:
        self.identity_run.click()
        expect(self.identity_status).to_have_text("Verified")

    def run_eligibility_check(self) -> None:
        self.eligibility_run.click()
        expect(self.eligibility_status).to_have_text("Eligible")


class DependentsStep(EnrollStep):
    """Step 4: dependents on the draft."""

    RELATIONSHIP = {"Child": "CHILD", "Spouse": "SPOUSE", "Domestic partner": "DOMESTIC_PARTNER"}

    @property
    def heading(self) -> Locator:
        return self.content.get_by_role("heading", name="Dependents on this draft")

    @property
    def item(self) -> Locator:
        """All dependents listed under "Dependents on this draft"."""
        return self.content.get_by_role("listitem")

    def item_named(self, name: str) -> Locator:
        return self.item.filter(has_text=name)

    @property
    def min_age_error(self) -> Locator:
        """The age rule for spouses and domestic partners."""
        return self.content.get_by_role("alert").filter(has_text="A spouse or domestic partner must be at least 18")

    def pick_relationship(self, relationship: str) -> None:
        self.test_id("dependent-relationship").click()
        self.test_id(f"dependent-relationship-{self.RELATIONSHIP[relationship]}").click()

    def describe(self, first_name: str, last_name: str, date_of_birth: str, relationship: str) -> None:
        """Fill the "Add a dependent" form; does not submit it."""
        self.test_id("dependent-first-name").fill(first_name)
        self.test_id("dependent-last-name").fill(last_name)
        self.test_id("dependent-dob").fill(date_of_birth)
        self.pick_relationship(relationship)

    def submit(self) -> None:
        self.test_id("dependent-add").click()

    def add(self, first_name: str, last_name: str, date_of_birth: str, relationship: str) -> None:
        """Add a dependent. Waits until the confirmation toast is shown."""
        self.describe(first_name, last_name, date_of_birth, relationship)
        self.submit()
        expect(self.status_with(f"{first_name} {last_name} added.")).to_be_visible()

    def remove(self, name: str) -> None:
        """Remove a dependent (Remove opens an in-row confirm)."""
        row = self.item_named(name)
        row.get_by_role("button", name=f"Remove {name}").click()
        row.get_by_role("button", name="Confirm removal").click()
        expect(self.status_with(f"{name} removed.")).to_be_visible()


class PlanStep(EnrollStep):
    """Step 5: plan catalog with tier filters."""

    TIERS = ("all", "silver", "gold", "bronze", "platinum")

    @property
    def cards(self) -> Locator:
        return self.content.locator("div[role='article']")

    def card(self, name: str) -> Locator:
        # Playwright re-roots the `has` locator at each outer match, so the
        # inner locator must start from the page, not from step-content.
        return self.cards.filter(
            has=self.page.get_by_role("heading", name=name, exact=True)
        )

    def filtered_by_tier(self, tier: str) -> Locator:
        """The plan cards of one tier (their subtitle reads "Tier \u00b7 ...")."""
        return self.cards.filter(has_text=f"{tier} \u00b7 ")

    def filter_by(self, tier: str) -> None:
        assert tier in self.TIERS
        self.test_id(f"plan-filter-{tier}").click()

    def selected_badge(self, name: str) -> Locator:
        return self.card(name).get_by_text("Selected", exact=True)

    def select(self, name: str) -> None:
        """Select a plan; the app saves the choice straight away."""
        self.card(name).get_by_role("button", name="Select Plan").click()
        expect(self.status_with("Plan selection saved.")).to_be_visible()


class DocumentsStep(EnrollStep):
    """Step 6: member documents."""

    @property
    def error(self) -> Locator:
        return self.test_id("document-error")

    @property
    def rows(self) -> Locator:
        return self.page.get_by_test_id("document-row")

    def row_for(self, filename: str) -> Locator:
        return self.rows.filter(has_text=filename)

    def upload(self, file_path: str) -> None:
        self.test_id("document-upload-input").set_input_files(file_path)


class ReviewStep(EnrollStep):
    """Step 7: review, HIPAA consent and submission."""

    SECTIONS = ("profile", "address", "verification", "dependents", "plan", "documents")

    @property
    def not_ready(self) -> Locator:
        """The "Before you can submit: ..." checklist."""
        return self.test_id("review-not-ready")

    @property
    def submit(self) -> Locator:
        return self.test_id("submit-enrollment")

    @property
    def enrollment_status(self) -> Locator:
        return self.test_id("enrollment-status")

    @property
    def consent_status(self) -> Locator:
        return self.test_id("consent-status")

    @property
    def consent_notice_version(self) -> Locator:
        return self.test_id("consent-notice-version")

    @property
    def consent_box(self) -> Locator:
        return self.test_id("consent-checkbox")

    @property
    def accept_consent_button(self) -> Locator:
        return self.test_id("consent-accept")

    @property
    def consent_audit(self) -> Locator:
        return self.after_heading("Consent audit").locator("li")

    def section(self, name: str) -> Locator:
        assert name in self.SECTIONS
        return self.test_id(f"review-section-{name}")

    def edit_link(self, name: str) -> Locator:
        return self.test_id(f"review-edit-{name}")

    def accept_consent(self) -> None:
        """Tick the HIPAA box and record the consent (reverse not possible)."""
        self.consent_box.click()
        self.accept_consent_button.click()
        expect(self.consent_status).to_contain_text("Consent given")

    def submit_enrollment(self) -> None:
        self.submit.click()
