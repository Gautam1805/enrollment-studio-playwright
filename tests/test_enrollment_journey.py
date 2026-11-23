"""One applicant's complete enrollment, start to finish.

A single test that walks one person through every step of the wizard the
way a staff user would, moving on with each step's "Next" link:

  1 Profile -> 2 Address -> 3 Verification -> 4 Dependents -> 5 Plan
  -> 6 Documents -> 7 Review -> HIPAA consent -> Submit -> Applications

The detailed checks of each step (rejections, limits, edge cases) live in
test_new_enrollment.py; this file is the end-to-end journey, handy for a
demo:

    python -m pytest tests/test_enrollment_journey.py --headed --slowmo 500 -v -s

Each run creates one new, submitted application named
"AUTO-Lena Journey<random letters>" (names allow letters only), so the run
can find exactly its own application on the Applications page.
"""

import random
import string

from playwright.sync_api import expect

from pages.applications_page import ApplicationsPage
from pages.enrollment_draft import EnrollmentDraftPage
from pages.enrollment_steps import ProfileStep
from pages.side_nav import SideNav

PDF_HEAD = b"%PDF-1.4\n"
PLAN = "Gold Plus"


def say(text: str) -> None:
    """Narrate the journey in the terminal (shown with -s)."""
    print(f"\n  >> {text}", flush=True)


def test_one_applicant_completes_enrollment_end_to_end(applications: ApplicationsPage, tmp_path):
    """One applicant goes through all 7 steps, gives HIPAA consent, submits, and is listed as Submitted."""
    page = applications.page
    last_name = "Journey" + "".join(random.choices(string.ascii_lowercase, k=5))
    applicant = f"AUTO-Lena {last_name}"
    child = f"AUTO-Milo {last_name}"
    document_name = "AUTO-Lena-Income-Proof.pdf"
    document = tmp_path / document_name
    document.write_bytes(PDF_HEAD + b"A" * 200_000)

    say(f"Step 1 of 7, Profile: new enrollment for {applicant}")
    SideNav(page).start_new_enrollment()
    applications.wait_for_path("/enroll/new/profile")
    profile = ProfileStep(page)
    expect(profile.step_count).to_have_text("Step 1 of 7")
    profile.fill(dict(
        first_name="AUTO-Lena", last_name=last_name, date_of_birth="1988-09-23", ssn="345678901",
        email=f"auto.lena.{last_name.lower()}@example.com", phone="555-010-4477",
        address_line_1="12 Willow Street", city="Springfield", state="IL", zip_code="62704",
    ))
    profile.save()

    say("Step 2 of 7, Address: the saved residential address")
    draft = EnrollmentDraftPage.from_url(page).wait_for_step("address")
    expect(draft.address.saved_address).to_have_text("12 Willow Street, Springfield, IL 62704")

    say("Step 3 of 7, Verification: identity and eligibility checks")
    draft.go_next().wait_for_step("verification")
    draft.verification.run_identity_check()
    draft.verification.run_eligibility_check()
    expect(draft.verification.eligibility_code).to_contain_text("ELG-00")

    say(f"Step 4 of 7, Dependents: add a child, {child}")
    draft.go_next().wait_for_step("dependents")
    draft.dependents.add("AUTO-Milo", last_name, "2015-06-14", "Child")
    expect(draft.dependents.item_named(child)).to_contain_text("Child")

    say(f"Step 5 of 7, Plan: choose {PLAN}")
    draft.go_next().wait_for_step("plan")
    draft.plan.select(PLAN)
    expect(draft.plan.selected_badge(PLAN)).to_be_visible()

    say(f"Step 6 of 7, Documents: upload {document_name}")
    draft.go_next().wait_for_step("documents")
    draft.documents.upload(str(document))
    expect(draft.documents.row_for(document_name)).to_be_visible()
    expect(draft.documents.error).to_have_count(0)

    say("Step 7 of 7, Review: everything entered is summarised")
    draft.go_next().wait_for_step("review")
    review = draft.review
    expect(review.section("profile")).to_contain_text(applicant)
    expect(review.section("address")).to_contain_text("12 Willow Street, Springfield, IL 62704")
    expect(review.section("verification")).to_contain_text("Verified")
    expect(review.section("verification")).to_contain_text("Eligible")
    expect(review.section("dependents")).to_contain_text(child)
    expect(review.section("plan")).to_contain_text(PLAN)
    expect(review.section("documents")).to_contain_text(document_name)

    say("HIPAA consent: Submit stays disabled until consent is given")
    expect(review.submit).to_be_disabled()
    review.accept_consent()
    expect(review.consent_status).to_contain_text("Consent given")
    expect(review.submit).to_be_enabled()

    say("Submit the enrollment")
    review.submit_enrollment()
    expect(review.enrollment_status).to_have_text("SUBMITTED")

    say(f"Applications: {applicant} is listed as Submitted")
    applications.open()
    found = applications.search_for(last_name)
    expect(found).to_have_count(1)
    expect(found.first).to_contain_text(applicant)
    expect(found.first).to_contain_text("Submitted")
    say("Enrollment complete")
