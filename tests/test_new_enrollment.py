"""Story 145 — completing and submitting a new enrollment end to end
(TC 158-172). Each test runs its own journey draft, walked through the
wizard's real steps, and names it with the AUTO- convention; drafts the
tests create are deleted again (the app refuses for submitted ones).
"""

import base64
import random
import re
import string
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from pages.applications_page import ApplicationsPage, Status
from pages.enrollment_wizard_page import EnrollmentWizard
from support import config

#: The profile every journey draft uses — the story's AUTO-Marisol AUTO-Reyes.
PROFILE = {
    "first_name": "AUTO-Marisol",
    "last_name": "AUTO-Reyes",
    "dob": "1990-01-15",
    "ssn": "123456789",
    "email": "auto.marisol.reyes@example.test",
    "phone": "555-010-0100",
    "line1": "123 AUTO Test Avenue",
    "line2": "",
    "city": "AUTO Springs",
    "state": "AZ",
    "zip": "85001",
}

#: A ZIP the payer's region check answers ELG-00 (Eligible) for.
ELIGIBLE_ADDRESS = {
    "line1": "45 AUTO Eligible Road",
    "city": "AUTO Springfield",
    "state": "IL",
    "zip": "62704",
}

#: An address USPS cannot find: the 'Keep address as entered' subject.
NOWHERE_ADDRESS = {
    "line1": "99 AUTO Nowhere Lane",
    "city": "AUTO Hollow",
    "state": "AZ",
    "zip": "00000",
}

CHILD = {
    "first_name": "AUTO-Nia",
    "last_name": "AUTO-Reyes",
    "dob": "2015-06-01",
    "relationship": "Child",
    "relationship_value": "CHILD",
}

UNDERAGE_SPOUSE = {
    "first_name": "AUTO-Sam",
    "last_name": "AUTO-Reyes",
    "dob": "2016-06-01",
    "relationship": "Spouse",
    "relationship_value": "SPOUSE",
}

PLAN = "Silver Balance"

#: Uploaded size the app allows: up to 10 MB, so a byte or two under it.
UNDER_LIMIT = 9_961_472  # 9.5 MiB
OVER_LIMIT = 11_534_336  # 11 MiB

#: Big PDFs upload slowly; give the upload its own wait, beyond expect()'s 15 s.
UPLOAD_WAIT_MS = 120_000

#: The payer answers a submission after a few seconds; give the submit
#: acknowledgement its own wait, beyond expect()'s 15 s.
SUBMIT_WAIT_MS = 60_000

#: A 1x1 pixel JPEG, the smallest valid image the Documents step accepts.
_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
    "Hh0aHBwcJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAAB"
    "AQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAA"
    "AAAAAP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AJgA/9k="
)


def _submitted_identity() -> dict:
    """A person the payer has never seen, fresh every run: the app refuses
    to delete submitted applications and the payer answers a second
    enrollment of the same person with 'Rejected: duplicate member'
    (SUB-03). Letters-only 'AUTO-' suffixed names keep the profile rules
    and make the application searchable by its unique first name.

    The SSN is drawn from the digits 2-8 only. The payer's identity
    service answers each SSN band deterministically: a serial in
    9000-9999 gets 'Partial match: manual review required' (PARTIAL), a
    0000 serial gets 'SSN failed validation' (FAILED): either would fail
    the identity check. Digits 2-8 keep the SSN outside both bands
    (7^8 combinations, still fresh per run)."""
    letters = "".join(random.choices(string.ascii_uppercase, k=6))
    return {
        "first_name": f"AUTO-{letters}",
        "last_name": f"AUTO-Reyes-{letters}",
        "email": f"auto.marisol.reyes.{letters.lower()}@example.test",
        "ssn": "1" + "".join(random.choices("2345678", k=8)),
        "phone": "555-010-" + "".join(random.choices("23456789", k=4)),
    }


def valid_pdf(total_size: int) -> bytes:
    """A valid single-page PDF padded with spaces to `total_size` bytes:
    header, four objects, and a final EOF (the shape the app accepts)."""
    head = b"%PDF-1.4\n"
    stream_len = total_size - len(head) - 400
    body = b"".join([
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << >> >>\nendobj\n",
        b"4 0 obj\n<< /Length " + str(stream_len).encode() + b" >>\nstream\n"
        + b" " * stream_len + b"\nendstream\nendobj\n",
    ])
    return head + body + b"%%EOF"


@pytest.fixture
def wizard(staff_page: Page) -> EnrollmentWizard:
    """A wizard on the signed-in page."""
    return EnrollmentWizard(staff_page)


@pytest.fixture
def new_draft(wizard: EnrollmentWizard):
    """`new_draft(**address_overrides)` starts a fresh AUTO-Marisol
    AUTO-Reyes draft (saved at step 1) and deletes it after the test."""

    created: list[str] = []

    def start(**address_overrides) -> EnrollmentWizard:
        wizard.open_new()
        wizard.fill_profile({**PROFILE, **address_overrides})
        wizard.save_profile()
        created.append(wizard.member_id)
        return wizard

    yield start

    for member_id in reversed(created):
        try:
            wizard.page.request.delete(f"{config.BASE_URL}/api/members/{member_id}")
        except Exception:  # the app refuses to delete a submitted enrollment
            pass


def run_identity_check(wizard: EnrollmentWizard) -> None:
    """Run the identity check and wait for its answer."""
    wizard.run_identity_check()
    expect(wizard.status_after("Identity Status")).to_have_text("Verified")


def run_eligibility_check(wizard: EnrollmentWizard) -> None:
    """Run the eligibility check until the payer says Eligible. The check
    can time out; the app allows at most three attempts, so try at most
    three times, then give up."""
    status = wizard.status_after("Eligibility Status")
    for _ in range(3):
        wizard.run_eligibility_check()
        try:
            expect(status).to_have_text("Eligible", timeout=10_000)
            return
        except AssertionError:
            pass
    pytest.fail("eligibility was not Eligible after 3 attempts")


def journey(new_draft, to: str, *, child: bool = False, plan: str | None = None,
            documents: tuple[Path, ...] = (), identity: dict | None = None) -> EnrollmentWizard:
    """A story journey: a fresh draft walked with real steps to `to`
    (Address, Verification, Dependents, Plan, Documents or Review).
    The draft passes Verification with both checks run, and carries the
    child, plan and documents it is asked for; `identity` overrides the
    applicant's profile fields (used by the test that enrols it)."""
    wizard = new_draft(**{**ELIGIBLE_ADDRESS, **(identity or {})})
    if to != "address":
        wizard.continue_on()  # Address -> Verification
        run_identity_check(wizard)
        run_eligibility_check(wizard)
    if to in ("address", "verification"):
        return wizard
    wizard.continue_on()  # Verification -> Dependents
    if to == "dependents":
        return wizard
    if child:
        wizard.add_dependent(CHILD)
        expect(wizard.dependent("AUTO-Nia AUTO-Reyes").first).to_be_visible()
    wizard.continue_on()  # Dependents -> Plan
    if to == "plan":
        return wizard
    if plan:
        wizard.select_plan(plan)
        expect(wizard.plan_saved_message).to_be_visible()
    wizard.continue_on()  # Plan -> Documents
    if to == "documents":
        return wizard
    for path in documents:
        wizard.upload_document(path)
        expect(wizard.uploaded(path.name)).to_be_visible(timeout=UPLOAD_WAIT_MS)
    wizard.continue_on()  # Documents -> Review
    return wizard


@pytest.fixture
def documents(tmp_path: Path) -> dict[str, Path]:
    """The test files the Documents step uses, in a temporary directory."""
    pdf = tmp_path / "AUTO-enrollment-form.pdf"
    pdf.write_bytes(valid_pdf(UNDER_LIMIT))
    jpg = tmp_path / "AUTO-id-card.jpg"
    jpg.write_bytes(_JPEG)
    txt = tmp_path / "AUTO-notes.txt"
    txt.write_bytes(b"AUTO test notes, not a PDF or an image\n")
    oversize = tmp_path / "AUTO-oversize-scan.pdf"
    oversize.write_bytes(valid_pdf(OVER_LIMIT))
    return {"pdf": pdf, "jpg": jpg, "txt": txt, "oversize": oversize}


def test_complete_profile_saves_draft_and_opens_address(new_draft):
    """TC 158: Saving a complete profile creates a draft and opens Address
    with the saved address, status 'Not verified'."""
    wizard = new_draft()

    expect(wizard.saved_address).to_have_text("123 AUTO Test Avenue, AUTO Springs, AZ 85001")
    expect(wizard.saved_address_status).to_have_text("Not verified")


def test_profile_rejects_8_digit_ssn(wizard):
    """TC 159: An SSN with 8 digits is rejected; no draft is saved."""
    wizard.open_new()
    wizard.fill_profile({**PROFILE, "ssn": "12345678"})
    wizard.save.click()

    assert wizard.current_path() == EnrollmentWizard.PATH, "the wizard should still be on step 1"
    expect(wizard.save_blocked("SSN must be 9 digits")).to_be_visible()


def test_profile_rejects_first_name_with_digit(wizard):
    """TC 160: A first name containing a digit is rejected; no draft is saved."""
    wizard.open_new()
    wizard.fill_profile({**PROFILE, "first_name": "AUTO-Mar1sol"})
    wizard.save.click()

    assert wizard.current_path() == EnrollmentWizard.PATH, "the wizard should still be on step 1"
    expect(wizard.save_blocked(
        "First name can only contain letters, spaces, hyphens, apostrophes and periods")).to_be_visible()


def test_address_override_keeps_address_usps_cannot_find(new_draft):
    """TC 161: 'Keep address as entered' saves an address USPS cannot find,
    with status 'Kept as entered (override)' and a history entry."""
    wizard = new_draft(**NOWHERE_ADDRESS)
    expect(wizard.saved_address_status).to_have_text("Not verified")

    wizard.validate_address()
    expect(wizard.address_not_found).to_be_visible()
    expect(wizard.keep_as_entered_button).to_be_visible()

    wizard.keep_as_entered("AUTO-test override")

    expect(wizard.saved_address).to_contain_text("99 AUTO Nowhere Lane")
    expect(wizard.saved_address).to_contain_text("AUTO Hollow")
    expect(wizard.saved_address).to_contain_text("00000")
    expect(wizard.saved_address_status).to_have_text("Kept as entered (override)")

    history = wizard.address_history_items.first
    expect(history).to_contain_text("Kept as entered")
    expect(history).to_contain_text("AUTO-test override")


def test_verification_identity_verified_and_eligibility_eligible(new_draft):
    """TC 162: Identity check answers Verified; eligibility answers Eligible
    (ELG-00); both are recorded in their audit lists."""
    wizard = journey(new_draft, "verification")

    expect(wizard.eligibility_code).to_contain_text("ELG-00")
    expect(wizard.eligibility_audit_items.first).to_contain_text("ELG-00")
    expect(wizard.identity_audit_items.first).to_contain_text("VERIFIED")


def test_dependent_child_under_26_is_added(new_draft):
    """TC 163: A child under 26 is added and listed under
    'Dependents on this draft' with the entered name, birth and relationship."""
    wizard = journey(new_draft, "dependents")

    wizard.add_dependent(CHILD)

    expect(wizard.dependent("AUTO-Nia AUTO-Reyes").first).to_contain_text("Child · Born Jun 1, 2015")
    expect(wizard.step_content.get_by_role("status").filter(
        has_text="AUTO-Nia AUTO-Reyes added.")).to_be_visible()


def test_dependents_step_continues_without_dependents(new_draft):
    """TC 164: Dependents are optional: with no dependent added, 'Continue'
    moves the wizard on to step 5 of 7 (Plan Selection)."""
    wizard = journey(new_draft, "dependents")
    expect(wizard.dependents_items).to_have_count(0)

    wizard.continue_on()  # Dependents -> Plan

    assert wizard.current_step == "plan"
    expect(wizard.step_link("plan")).to_have_attribute("aria-current", "step")
    expect(wizard.step_content.get_by_role("heading", name="Plan Selection", exact=True)).to_be_visible()


def test_underage_spouse_is_rejected(new_draft):
    """TC 165: A spouse younger than 18 is rejected with 'A spouse or
    domestic partner must be at least 18' and is not added."""
    wizard = journey(new_draft, "dependents")

    wizard.add_dependent(UNDERAGE_SPOUSE)

    expect(wizard.save_blocked("A spouse or domestic partner must be at least 18")).to_be_visible()
    expect(wizard.dependents_items).to_have_count(0)


def test_plan_tier_filter_and_selection_saved(new_draft):
    """TC 166: The tier filter lists only matching plans, 'All' lists them
    all again, and the plan chosen is saved ('Plan selection saved')."""
    wizard = journey(new_draft, "plan")

    wizard.plan_filter("gold").click()
    expect(wizard.plan_card("Gold Plus")).to_be_visible()
    expect(wizard.plan_card("Silver Balance")).to_have_count(0)
    expect(wizard.plan_card("Bronze Basic")).to_have_count(0)

    wizard.plan_filter("all").click()
    expect(wizard.step_content.get_by_role("article")).to_have_count(5)
    expect(wizard.plan_card("Silver Balance")).to_be_visible()

    wizard.select_plan("Gold Plus")

    expect(wizard.plan_saved_message).to_be_visible()
    selected = wizard.plan_card("Gold Plus").get_by_role("button", name="Selected Plan")
    expect(selected).to_be_disabled()


def test_documents_accept_pdf_and_jpg_within_limit(new_draft, documents):
    """TC 167: A PDF just under the 10 MB limit and a small JPG upload and
    are listed for the member."""
    wizard = journey(new_draft, "documents")

    wizard.upload_document(documents["pdf"])
    expect(wizard.uploaded("AUTO-enrollment-form.pdf")).to_be_visible(timeout=UPLOAD_WAIT_MS)

    wizard.upload_document(documents["jpg"])
    expect(wizard.uploaded("AUTO-id-card.jpg")).to_be_visible()
    expect(wizard.uploaded_items).to_have_count(2)


def test_documents_reject_unsupported_file_type(new_draft, documents):
    """TC 168: A plain text file is rejected as an unsupported file type and
    is not listed for the member."""
    wizard = journey(new_draft, "documents")

    wizard.upload_document(documents["txt"])

    expect(wizard.upload_alert.filter(
        has_text="Could not upload AUTO-notes.txt: Unsupported file type")).to_be_visible()
    expect(wizard.uploaded("AUTO-notes.txt")).to_have_count(0)
    expect(wizard.uploaded_items).to_have_count(0)


def test_documents_reject_file_over_10mb(new_draft, documents):
    """TC 169: A PDF larger than 10 MB is rejected with 'File exceeds
    10MB limit' and is not listed."""
    wizard = journey(new_draft, "documents")

    wizard.upload_document(documents["oversize"])

    expect(wizard.upload_alert.filter(
        has_text="Could not upload AUTO-oversize-scan.pdf: File exceeds 10MB limit")).to_be_visible()
    expect(wizard.uploaded("AUTO-oversize-scan.pdf")).to_have_count(0)
    expect(wizard.uploaded_items).to_have_count(0)


def test_review_summarises_all_six_sections_with_edit_links(new_draft, documents):
    """TC 170: Review summarises Profile, Address, Verification,
    Dependents, Plan and Documents with the saved AUTO- data, each with an
    Edit link."""
    wizard = journey(new_draft, "review", child=True, plan=PLAN,
                     documents=(documents["pdf"], documents["jpg"]))

    expect(wizard.review_section("profile")).to_contain_text("AUTO-Marisol AUTO-Reyes")
    expect(wizard.review_section("profile")).to_contain_text("auto.marisol.reyes@example.test")
    expect(wizard.review_section("address")).to_contain_text(
        "45 AUTO Eligible Road, AUTO Springfield, IL 62704")
    expect(wizard.review_section("address")).to_contain_text("Not verified")
    expect(wizard.review_section("verification")).to_contain_text("Verified")
    expect(wizard.review_section("verification")).to_contain_text("Eligible")
    expect(wizard.review_section("dependents")).to_contain_text("AUTO-Nia AUTO-Reyes")
    expect(wizard.review_section("plan")).to_contain_text("Silver Balance")
    expect(wizard.review_section("plan")).to_contain_text("Silver")
    expect(wizard.review_section("documents")).to_contain_text("AUTO-enrollment-form.pdf")
    expect(wizard.review_section("documents")).to_contain_text("AUTO-id-card.jpg")

    for step in ("profile", "address", "verification", "dependents", "plan", "documents"):
        expect(wizard.review_edit(step)).to_have_text("Edit")


def test_hipaa_consent_gates_submission_and_app_is_submitted(new_draft, documents):
    """TC 171: Review shows 'Before you can submit: Give HIPAA consent'
    until the consent is accepted; accepting it records the notice version
    and time; Submit enrollment then submits, and the application shows as
    Submitted in Applications."""
    identity = _submitted_identity()  # the payer enrols a person once
    name = f"{identity['first_name']} {identity['last_name']}"
    wizard = journey(new_draft, "review", child=True, plan=PLAN,
                     documents=(documents["jpg"],), identity=identity)
    member_id = wizard.member_id  # the applications assertions need this later

    expect(wizard.not_ready).to_contain_text("Give HIPAA consent for the current notice")
    expect(wizard.submit).to_be_disabled()

    wizard.accept_consent()

    expect(wizard.consent_status).to_contain_text("Consent given (v1.1) on")
    expect(wizard.consent_card.get_by_role("time")).to_be_visible()
    expect(wizard.consent_audit_items.first).to_contain_text("v1.1")
    expect(wizard.consent_audit_items.first).to_contain_text("Given")

    wizard.page.reload()  # once consent is recorded the app drops the gate alert

    expect(wizard.not_ready).to_have_count(0)
    expect(wizard.submit).to_be_enabled()

    wizard.submit_enrollment()

    # The payer's answer takes a few seconds and the review page re-renders
    # itself; wait for it instead of reloading, which would abort the submit
    # request and leave the chip at DRAFT. Criterion 11 is judged where the
    # story states it: the Submitted row in Applications below.
    expect(wizard.enrollment_status).to_have_text(
        re.compile("SUBMITTED|REJECTED"), timeout=SUBMIT_WAIT_MS)

    applications = ApplicationsPage(wizard.page).open()
    applications.filter_by_status(Status.SUBMITTED).set_search(identity["first_name"])
    row = applications.row_for(name).first
    expect(applications.row_link(row)).to_have_attribute(
        "href", re.compile(f"/enroll/{re.escape(member_id)}/"))
    expect(applications.row_status(row)).to_have_text("Submitted")


def test_accepted_hipaa_consent_cannot_be_withdrawn(new_draft, documents):
    """TC 172: Once accepted, the consent stays recorded with its notice
    version and time and no way to withdraw or undo it is offered."""
    wizard = journey(new_draft, "review", plan=PLAN, documents=(documents["jpg"],))

    wizard.accept_consent()
    expect(wizard.consent_status).to_contain_text("Consent given (v1.1) on")

    wizard.page.reload()

    expect(wizard.consent_status).to_contain_text("Consent given (v1.1) on")
    expect(wizard.consent_status).to_contain_text("It cannot be withdrawn")
    expect(wizard.consent_status).to_contain_text("v1.1")
    expect(wizard.consent_audit_items.first).to_contain_text("v1.1")
    expect(wizard.consent_card.get_by_role("button")).to_have_count(0)
