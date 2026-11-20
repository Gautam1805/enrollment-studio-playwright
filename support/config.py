"""Settings, with environment overrides. Credentials come only from the environment."""

import os

#: The application under test.
BASE_URL = os.environ.get("APP_URL", "https://member-enrollment-demo.emids-assure.workers.dev").rstrip("/")

#: Signing in is the app's slowest step; it gets its own, longer wait (ms).
SIGN_IN_TIMEOUT_MS = 45_000

#: How long expect() and actions wait by default (ms).
DEFAULT_TIMEOUT_MS = 15_000


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise RuntimeError(f"set the {name} environment variable (see README)")
    return value


def username() -> str:
    return _required("ENROLL_USERNAME")


def password() -> str:
    return _required("ENROLL_PASSWORD")
