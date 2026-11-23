"""The new-enrollment wizard: the seven steps a draft walks from Profile to
Review (story 145). It starts at /enroll/new/profile; once a profile is
saved the URL carries the draft's id and the wizard opens a page per step.

Locators follow the app's own step test ids (`input-*`, `address-*`,
`identity-*`, ...) plus the shared wizard frame (`step-*`, `step-content`).
"""

import re
from pathlib import Path

from playwright.sync_api import Locator, expect

from pages.base_page import BasePage

#: Where a brand-new wizard starts.
NEW_PATH = "/enroll/new/profile"

#: /enroll/<draft-id>/<step> is the wizard's URL once a draft exists.
DRAFT_URL = re.compile(r"/enroll/([0-9a-f-]{36})(?:/([a-z]+))?$")

#: The wizard's steps, in order: step 1 to 7.
STEPS = ("profile", "address", "verification", "dependents", "plan", "documents", "review")


def _step_in_url(step: str):
    """A URL predicate: the wizard is on `step` (new or saved draft)."""
    pattern = re.compile(rf"/enroll/[^/]+/{step}/?$")

    def matches(url: str) -> bool:
        return pattern.search(url) is not None

    return matches


class EnrollmentWizard(BasePage):
    """One wizard. open_new() starts a brand-new draft; step actions move
    it on. The draft's id is read from the URL as soon as it is saved."""

    PATH = NEW_PATH

    # ---- moving around ---------------------------------------------------

    @property
    def member_id(self) -> str:
        """The draft's id from the URL (its stable identity)."""
        match = DRAFT_URL.search(self.page.url)
        if not match:
            raise RuntimeError(f"the wizard at {self.page.url} has no saved draft yet")
        return match.group(1)

    @property
    def current_step(self) -> str:
        match = DRAFT_URL.search(self.page.url)
        if match and match.group(2):
            return match.group(2)
        return "profile"

    @property
    def step_content(self) -> Locator:
        return self.test_id("step-content")

    def step_link(self, step: str) -> Locator:
        """The numbered entry in the step rail for `step`."""
        return self.test_id(f"step-{step}")

    def wait_until_on(self, step: str) -> "EnrollmentWizard":
        """Wait for the wizard to be on `step` of 7."""
        self.page.wait_for_url(_step_in_url(step))
        expect(self.step_link(step)).to_be_visible()
        return self

    def open_new(self) -> "EnrollmentWizard":
        """Start a brand-new, unsaved wizard at step 1 (Profile)."""
        self.page.goto(NEW_PATH)
        return self.wait_until_on("profile")

    def open_step(self, step: str) -> "EnrollmentWizard":
        """Reopen a saved draft directly on `step`."""
        self.page.goto(f"/enroll/{self.member_id}/{step}")
        return self.wait_until_on(step)

    def continue_on(self) -> "EnrollmentWizard":
        """Click the step's 'Next' link and land on the following step."""
        previous = self.current_step
        self.test_id("step-next").click()

        def moved(url: str) -> bool:
            match = DRAFT_URL.search(url)
            step = match.group(2) if match else "profile"
            return bool(match) and step != previous

        self.page.wait_for_url(moved)
        return self.on_next_step()

    def on_next_step(self) -> "EnrollmentWizard":
        """Wait the next step's page in; returns the wizard (chainable)."""
        return self.wait_until_on(self.current_step)

    @property
    def field_alert(self) -> Locator:
        """A step's inline field rejections, whatever the field."""
        return self.step_content.get_by_role("alert")

    # ---- step 1: Profile ---------------------------------------------------

    @property
    def first_name(self) -> Locator:
        return self.test_id("input-first-name")

    @property
    def last_name(self) -> Locator:
        return self.test_id("input-last-name")

    @property
    def date_of_birth(self) -> Locator:
        return self.test_id("input-date-of-birth")

    @property
    def ssn(self) -> Locator:
        return self.test_id("input-ssn-full-to-set-update")

    @property
    def email(self) -> Locator:
        return self.test_id("input-email")

    @property
    def phone(self) -> Locator:
        return self.test_id("input-phone")

    @property
    def address_line1(self) -> Locator:
        return self.test_id("input-address-line-1")

    @property
    def address_line2(self) -> Locator:
        return self.test_id("input-address-line-2")

    @property
    def city(self) -> Locator:
        return self.test_id("input-city")

    @property
    def state(self) -> Locator:
        return self.test_id("input-state")

    @property
    def zip_code(self) -> Locator:
        return self.test_id("input-zip-code")

    @property
    def save(self) -> Locator:
        return self.test_id("member-save")

    def fill_profile(self, data: dict) -> None:
        """Fill the profile form. Keys: first_name, last_name, dob, ssn,
        email, phone, line1, line2, city, state, zip."""
        self.first_name.fill(data["first_name"])
        self.last_name.fill(data["last_name"])
        self.date_of_birth.fill(data["dob"])
        self.ssn.fill(data["ssn"])
        self.email.fill(data["email"])
        self.phone.fill(data["phone"])
        self.address_line1.fill(data["line1"])
        self.address_line2.fill(data.get("line2", ""))
        self.city.fill(data["city"])
        self.state.fill(data["state"])
        self.zip_code.fill(data["zip"])

    def save_profile(self) -> "EnrollmentWizard":
        """Click 'Save and continue': the draft is created, step 2 opens."""
        self.save.click()
        return self.wait_until_on("address")

    def save_blocked(self, message: str) -> Locator:
        """A field rejection named `message` that keeps the wizard on step 1."""
        return self.field_alert.filter(has_text=message)

    # ---- step 2: Address ---------------------------------------------------

    @property
    def saved_address_panel(self) -> Locator:
        """The card showing the saved residential address and its status."""
        return self.page.get_by_role("heading", name="Saved address", exact=True).locator("xpath=..")

    @property
    def saved_address(self) -> Locator:
        """The saved address, one line: '123 Street, City, ST 00000'."""
        return self.saved_address_panel.get_by_role("definition").first

    @property
    def saved_address_status(self) -> Locator:
        """Its status chip: Not verified, Verified, Kept as entered (override)."""
        return self.saved_address_panel.locator('[data-slot="badge"]').first

    def validate_address(self) -> "EnrollmentWizard":
        self.test_id("address-validate").click()
        return self

    @property
    def address_not_found(self) -> Locator:
        return self.step_content.get_by_role("heading", name="Address not found")

    @property
    def override_reason(self) -> Locator:
        return self.test_id("address-override-reason")

    @property
    def keep_as_entered_button(self) -> Locator:
        return self.test_id("address-override-submit")

    def keep_as_entered(self, reason: str) -> "EnrollmentWizard":
        """'Keep address as entered' with the requested reason."""
        self.override_reason.fill(reason)
        self.keep_as_entered_button.click()
        return self

    @property
    def address_history_items(self) -> Locator:
        """Address history's entries ('No address changes logged yet' = none)."""
        return self.page.get_by_role("list", name="Address history").get_by_role("listitem")

    # ---- step 3: Verification ------------------------------------------------

    @property
    def identity_check(self) -> Locator:
        return self.test_id("identity-check")

    @property
    def eligibility_check(self) -> Locator:
        return self.test_id("eligibility-check")

    @property
    def eligibility_code(self) -> Locator:
        return self.test_id("eligibility-code")

    def status_after(self, heading: str) -> Locator:
        """The badge that follows a status heading ('Identity Status')."""
        return (self.page.get_by_role("heading", name=heading, exact=True)
                .locator("xpath=..").locator('[data-slot="badge"]').first)

    @property
    def identity_audit_items(self) -> Locator:
        return self.page.get_by_role("list", name="Identity Audit").get_by_role("listitem")

    @property
    def eligibility_audit_items(self) -> Locator:
        return self.page.get_by_role("list", name="Eligibility Audit").get_by_role("listitem")

    def run_identity_check(self) -> "EnrollmentWizard":
        self.identity_check.click()
        return self

    def run_eligibility_check(self) -> "EnrollmentWizard":
        self.eligibility_check.click()
        return self

    # ---- step 4: Dependents ----------------------------------------------------

    @property
    def dependent_first_name(self) -> Locator:
        return self.test_id("dependent-first-name")

    @property
    def dependent_last_name(self) -> Locator:
        return self.test_id("dependent-last-name")

    @property
    def dependent_date_of_birth(self) -> Locator:
        return self.test_id("dependent-dob")

    @property
    def dependents_items(self) -> Locator:
        return self.page.get_by_role("list", name="Dependents on this draft").get_by_role("listitem")

    def choose_relationship(self, label: str, value: str) -> "EnrollmentWizard":
        """Open the Relationship combobox and pick an option by value."""
        self.test_id("dependent-relationship").click()
        self.test_id(f"dependent-relationship-{value}").click()
        return self

    def add_dependent(self, data: dict) -> "EnrollmentWizard":
        """Fill the dependent form and click 'Add dependent'. Keys:
        first_name, last_name, dob, relationship, relationship_value."""
        self.dependent_first_name.fill(data["first_name"])
        self.dependent_last_name.fill(data["last_name"])
        self.dependent_date_of_birth.fill(data["dob"])
        self.choose_relationship(data["relationship"], data["relationship_value"])
        self.test_id("dependent-add").click()
        return self

    def dependent(self, name: str) -> Locator:
        """'Dependents on this draft' rows mentioning `name`."""
        return self.dependents_items.filter(has_text=name)

    # ---- step 5: Plan Selection ------------------------------------------------

    def plan_filter(self, tier: str) -> Locator:
        """The tier filter button ('all', 'silver', 'gold', ...)."""
        return self.test_id(f"plan-filter-{tier}")

    def plan_card(self, name: str) -> Locator:
        return self.page.get_by_role("article", name=name, exact=True)

    def plan_select(self, card: Locator) -> Locator:
        """`card`'s Select Plan button; it reads 'Selected Plan' once chosen."""
        return card.get_by_role("button", name="Select Plan", exact=True)

    @property
    def plan_saved_message(self) -> Locator:
        return self.step_content.get_by_role("status").filter(has_text="Plan selection saved")

    def select_plan(self, name: str) -> "EnrollmentWizard":
        card = self.plan_card(name)
        self.plan_select(card).click()
        return self

    # ---- step 6: Documents -------------------------------------------------------

    @property
    def document_upload(self) -> Locator:
        return self.test_id("document-upload-input")

    def upload_document(self, path: Path | str) -> None:
        self.document_upload.set_input_files(str(path))

    @property
    def uploaded_items(self) -> Locator:
        return self.page.get_by_role("list", name="Uploaded documents").get_by_role("listitem")

    def uploaded(self, name: str) -> Locator:
        return self.uploaded_items.filter(has_text=name)

    @property
    def upload_alert(self) -> Locator:
        return self.field_alert.filter(has_text="Could not upload")

    # ---- step 7: Review ------------------------------------------------------------

    def review_section(self, step: str) -> Locator:
        return self.test_id(f"review-section-{step}")

    def review_edit(self, step: str) -> Locator:
        return self.test_id(f"review-edit-{step}")

    @property
    def not_ready(self) -> Locator:
        return self.test_id("review-not-ready")

    @property
    def consent_card(self) -> Locator:
        return self.test_id("consent-card")

    @property
    def consent_status(self) -> Locator:
        """The recorded consent line ('Consent given (v1.1) on <time>.
        It cannot be withdrawn.' once accepted; 'Consent not given yet.')."""
        return self.test_id("consent-status")

    @property
    def consent_checkbox(self) -> Locator:
        return self.test_id("consent-checkbox")

    @property
    def consent_accept(self) -> Locator:
        return self.test_id("consent-accept")

    @property
    def consent_audit_items(self) -> Locator:
        return self.page.get_by_role("list", name="Consent audit").get_by_role("listitem")

    @property
    def submission_audit(self) -> Locator:
        return self.test_id("submission-audit-card")

    @property
    def submit(self) -> Locator:
        return self.test_id("submit-enrollment")

    @property
    def enrollment_status(self) -> Locator:
        """The application's status chip (e.g. 'SUBMITTED') on the review page."""
        return self.test_id("enrollment-status")

    def accept_consent(self) -> "EnrollmentWizard":
        """Tick 'I have read the HIPAA notice ...' and Accept consent."""
        self.consent_checkbox.click()
        self.consent_accept.click()
        return self

    def submit_enrollment(self) -> None:
        self.submit.click()
