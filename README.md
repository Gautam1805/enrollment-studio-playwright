# Member Enrollment Studio – UI automation (Playwright)

Playwright + Python + pytest (pytest-playwright), page object model.

## Layout

```
conftest.py        fixtures: staff_page (signed in once per session, reused), applications
pages/             page objects (BasePage holds test_id, heading and path helpers)
  side_nav.py        the sidebar shared by signed-in pages
support/config.py  base URL, timeouts, credentials from the environment
tests/             test modules (test_<area>.py)
pytest.ini         test paths, browser, markers
```

## Conventions

- Locate elements by `data-testid` with `get_by_test_id(...)` (`BasePage.test_id`) when the app has one; otherwise a short CSS selector.
- Page objects expose locators and actions (`sign_in`, `nav.open(...)`); assertions live in tests.
- Assert with Playwright's `expect(...)`, which waits. No `time.sleep`, no `wait_for_timeout`.
- Signed-in tests take the `applications` or `staff_page` fixture instead of signing in themselves.
- One behaviour per test function, with a docstring saying what it checks.
- Test data that a test creates is named with an `AUTO-` prefix so it is easy to find and remove.

## Running

Credentials are never committed. Set them in the environment:

```bash
pip install -r requirements.txt
python -m playwright install chromium
export ENROLL_USERNAME=...   # PowerShell: $env:ENROLL_USERNAME="..."
export ENROLL_PASSWORD=...
pytest                         # whole suite, headless
pytest tests/test_login.py     # one module
pytest --headed                # watch the browser
```

`APP_URL` overrides the application's address.
