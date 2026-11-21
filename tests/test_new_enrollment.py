"""Completing a new enrollment end to end (story 27).

Every test works on a draft it starts itself (applicant names carry an
"AUTO-" prefix, easy to find). The app offers no draft deletion, so drafts
stay in Applications; dependents a test adds are removed again.
"""

import os

import pytest
from playwright.sync_api import Page, expect

from pages.applications_page import ApplicationsPage
from pages.enrollment_draft import EnrollmentDraftPage, start_new_draft
from pages.enrollment_steps import ProfileStep
from pages.side_nav import SideNav

PDF_HEAD = b"%PDF-1.4\n"
PNG_HEAD = b"\x89PNG\r\n\x1a\n"
MB = 1024 * 1024

#: The plan catalog is fixed (no plan can be renamed from the UI), so the
#: Gold-tier test plan is the catalog's "Gold Plus".
GOLD_PLAN = "Gold Plus"


@pytest.fixture
def make_document(tmp_path):
    """Write a file on disk: magic header plus padding, to an exact size."""

    def _make(name: str, head: bytes, size: int) -> str:
        if size < len(head):
            raise ValueError(f"{size} bytes is too small for a {name} header")
        path = tmp_path / name
        path.write_bytes(head + b"A" * (size - len(head)))
        return str(path)

    return _make


def profile(first_name, last_name, *, ssn, date_of_birth="1990-04-12", phone="555-010-1234",
            address_line_1="12 Willow Street", address_line_2="", city="Springfield", state="IL",
            zip_code="62704", email=None):
    """Required profile fields; the address is the residential one."""
    if email is None:
        email = f"auto.{last_name.lower()}@example.com"
    return dict(
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date_of_birth,
        ssn=ssn,
        email=email,
        phone=phone,
        address_line_1=address_line_1,
        address_line_2=address_line_2,
        city=city,
        state=state,
        zip_code=zip_code,
    )


def build_complete_draft(page: Page, profile_data: dict, *, dependent=None, document=None) -> EnrollmentDraftPage:
    """Push a fresh draft through the steps up to Review.

    Runs the identity and eligibility checks, then record the (optional)
    dependent and document, selects a plan and opens step 7, Review.
    """
    draft = start_new_draft(page, profile_data)
    draft.open_step("verification")
    draft.verification.run_identity_check()
    draft.verification.run_eligibility_check()
    if dependent is not None:
        first, last, date_of_birth, relationship = dependent
        draft.open_step("dependents")
        draft.dependents.add(first, last, date_of_birth, relationship)
    if document is not None:
        draft.open_step("documents")
        draft.documents.upload(document)
        expect(draft.documents.row_for(os.path.basename(document))).to_be_visible()
    draft.open_step("plan")
    draft.plan.select(GOLD_PLAN)
    return draft.open_step("review")


def test_saving_complete_profile_creates_draft_and_opens_address(applications: ApplicationsPage):
    """draft-1: a saved profile creates a draft and opens Address with status Not verified."""
    SideNav(applications.page).start_new_enrollment()
    applications.wait_for_path("/enroll/new/profile")
    form = ProfileStep(applications.page)

    expect(form.step_count).to_have_text("Step 1 of 7")
    expect(form.heading).to_be_visible()

    form.fill(profile("AUTO-Nadia", "Ro", ssn="123456789"))
    form.save()

    draft = EnrollmentDraftPage.from_url(applications.page).wait_for_step("address")
    expect(draft.address.step_count).to_have_text("Step 2 of 7")
    expect(draft.address.saved_address).to_have_text("12 Willow Street, Springfield, IL 62704")
    expect(draft.address.saved_status).to_have_text("Not verified")


def test_address_not_resolved_keeping_as_entered_records_override(applications: ApplicationsPage):
    """draft-2: USPS cannot resolve the address; keep-as-entered overrides and is logged."""
    draft = start_new_draft(
        applications.page,
        # The state must be filled in: without it the app refuses to even run
        # USPS ("State is required") and refuses the override too, so this is
        # not the criterion's "USPS cannot find the address" scenario. With a
        # state, USPS does run and cannot find QZXV 00000.
        profile("AUTO-Reva", "Skin", ssn="234567890", address_line_1="7 AUTO Unmatch Lane",
                city="QZXV", state="IL", zip_code="00000"),
    )
    address = draft.address

    address.validate.click()
    expect(address.not_found_heading).to_be_visible()
    expect(address.keep_option).to_be_visible()

    address.keep_as_entered("AUTO-Reva kept as entered: USPS records out of date")
    expect(address.saved_status).to_have_text("Kept as entered (override)")

    entry = address.history_entry("Kept as entered").filter(has_text="Reason: AUTO-Reva kept as entered")
    expect(entry.first).to_be_visible()


def test_identity_eligibility_checks_report_status_and_logged_in_audits(applications: ApplicationsPage):
    """draft-3: identity shows Verified, eligibility Eligible (ELG-00), both in their audit lists."""
    draft = start_new_draft(applications.page, profile("AUTO-Davu", "lens", ssn="345678901"))
    draft.open_step("verification")
    checks = draft.verification

    checks.run_identity_check()
    checks.run_eligibility_check()

    expect(checks.eligibility_code).to_contain_text("ELG-00")
    expect(checks.identity_audit.filter(has_text="Identity verified")).to_be_visible()
    expect(checks.eligibility_audit.filter(has_text="ELG-00")).to_be_visible()


def test_child_dependent_under_26_added_and_listed(applications: ApplicationsPage):
    """draft-4: a child under 26 can be added and appears under Dependents on this draft."""
    draft = start_new_draft(applications.page, profile("AUTO-Kai", "Nook", ssn="456789012"))
    draft.open_step("dependents")
    dependents = draft.dependents

    dependents.add("AUTO-Child", "AUTO-Dep", "2016-03-15", "Child")

    listed = dependents.item_named("AUTO-Child AUTO-Dep")
    expect(listed).to_be_visible()
    expect(listed).to_contain_text("Child · Born Mar 15, 2016")

    dependents.remove("AUTO-Child AUTO-Dep")  # test data starts with AUTO-; tidy up what we added
    expect(dependents.item_named("AUTO-Child AUTO-Dep")).to_have_count(0)


def test_spouse_younger_than_18_rejected(applications: ApplicationsPage):
    """draft-5: a spouse under 18 is not added and the age-rule message is shown.

    The suggested DOB in the case, 2008-07-01, makes the spouse 18 on the
    application's own clock (which runs ahead), so this test uses a DOB that
    is unmistakably under 18 there, 2012-05-20.
    """
    draft = start_new_draft(applications.page, profile("AUTO-Mira", "Holt", ssn="567890123"))
    draft.open_step("dependents")
    dependents = draft.dependents

    dependents.describe("AUTO-Spouse", "AUTO-Minor", "2012-05-20", "Spouse")
    dependents.submit()

    expect(dependents.min_age_error).to_be_visible()
    expect(dependents.item_named("AUTO-Spouse AUTO-Minor")).to_have_count(0)


def test_plan_tier_filter_and_saved_selection(applications: ApplicationsPage):
    """draft-6: Gold filter leaves only Gold plans, All shows them again; the
    selection is saved (the catalog is fixed, so the Gold plan is Gold Plus)."""
    draft = start_new_draft(applications.page, profile("AUTO-Rona", "Tire", ssn="678901234"))
    draft.open_step("plan")
    plans = draft.plan

    plans.filter_by("gold")
    expect(plans.status_with("1 plan in Gold")).to_be_visible()
    expect(plans.filtered_by_tier("Gold")).to_have_count(1)
    expect(plans.filtered_by_tier("Bronze")).to_have_count(0)

    plans.filter_by("all")
    expect(plans.status_with("5 plans available")).to_be_visible()
    expect(plans.cards).to_have_count(5)

    plans.select(GOLD_PLAN)
    expect(plans.selected_badge(GOLD_PLAN)).to_be_visible()

    draft.open_step("plan")  # the choice is kept when the step is reopened
    plans = draft.plan
    expect(plans.selected_badge(GOLD_PLAN)).to_be_visible()


def test_documents_pdf_and_file_at_10mb_limit_upload(applications: ApplicationsPage, make_document):
    """draft-7: a 1 MB PDF and one at exactly 10 MB upload and are listed."""
    draft = start_new_draft(applications.page, profile("AUTO-Dex", "Fold", ssn="789012345"))
    draft.open_step("documents")
    documents = draft.documents

    documents.upload(make_document("AUTO-Statement.pdf", PDF_HEAD, MB))
    expect(documents.row_for("AUTO-Statement.pdf")).to_be_visible()

    documents.upload(make_document("AUTO-Exact10MB.pdf", PDF_HEAD, 10 * MB))
    # A full 10 MB upload takes tens of seconds, well over the suite's default wait.
    expect(documents.row_for("AUTO-Exact10MB.pdf")).to_be_visible(timeout=90_000)

    expect(documents.error).to_have_count(0)  # neither upload was refused


def test_documents_txt_and_over_10mb_files_rejected(applications: ApplicationsPage, make_document):
    """draft-8: an unsupported type and an 11 MB image are refused and not listed."""
    draft = start_new_draft(applications.page, profile("AUTO-Priya", "Stack", ssn="890123456"))
    draft.open_step("documents")
    documents = draft.documents

    documents.upload(make_document("AUTO-Form.txt", b"AUTO enrollment form\n", 512))
    expect(documents.error).to_contain_text("Could not upload AUTO-Form.txt: Unsupported file type")
    expect(documents.row_for("AUTO-Form.txt")).to_have_count(0)

    documents.upload(make_document("AUTO-Scan-11MB.png", PNG_HEAD, 11 * MB))
    expect(documents.error).to_contain_text("Could not upload AUTO-Scan-11MB.png: File exceeds 10MB limit")
    expect(documents.row_for("AUTO-Scan-11MB.png")).to_have_count(0)


def test_review_summarises_all_six_areas_each_with_edit_link(applications: ApplicationsPage, make_document):
    """draft-9: Review names Profile, Address, Verification, Dependents,
    Plan and Documents, each with an Edit link and the details entered."""
    document = make_document("AUTO-Sena-Statement.pdf", PDF_HEAD, MB)
    draft = build_complete_draft(
        applications.page,
        profile("AUTO-Sena", "Field", ssn="901234567", address_line_1="74 AUTO Garden Road",
                city="Round Lake", state="IL", zip_code="60073"),
        dependent=("AUTO-Tiny", "AUTO-Field", "2018-02-20", "Child"),
        document=document,
    )
    review = draft.review

    for area in ("profile address verification dependents plan documents").split():
        expect(review.section(area)).to_be_visible()
        expect(review.edit_link(area)).to_be_visible()

    expect(review.section("profile")).to_contain_text("AUTO-Sena Field")
    expect(review.section("address")).to_contain_text("74 AUTO Garden Road, Round Lake, IL 60073")
    expect(review.section("verification")).to_contain_text("Verified")
    expect(review.section("verification")).to_contain_text("Eligible")
    expect(review.section("dependents")).to_contain_text("AUTO-Tiny AUTO-Field")
    expect(review.section("plan")).to_contain_text(GOLD_PLAN)
    expect(review.section("documents")).to_contain_text("AUTO-Sena-Statement.pdf")


def test_submit_blocked_until_consent_then_listed_as_submitted(applications: ApplicationsPage):
    """draft-10: submit waits for HIPAA consent; after consent the application
    lands in Applications with status Submitted."""
    draft = build_complete_draft(applications.page, profile("AUTO-Juno", "Race", ssn="012345678"))
    draft.open_step("review")
    review = draft.review
    assert draft.current_step() == "review"

    expect(review.submit).to_be_disabled()
    expect(review.not_ready).to_contain_text("Give HIPAA consent for the current notice")

    review.accept_consent()  # tick "I have read the HIPAA notice ..." then Accept
    expect(review.not_ready).to_have_count(0)
    expect(review.consent_notice_version).to_have_text("v1.1")
    expect(review.consent_status).to_contain_text("Consent given (v1.1)")
    expect(review.consent_status).to_contain_text("It cannot be withdrawn.")
    expect(review.consent_audit.filter(has_text="Given")).to_be_visible()

    review.submit_enrollment()
    expect(review.enrollment_status).to_have_text("SUBMITTED")

    applications.open()  # the submitted application is listed on Applications
    found = applications.search_for("AUTO-Juno")
    expect(found.first).to_contain_text("AUTO-Juno Race")
    expect(found.first).to_contain_text("Submitted")
