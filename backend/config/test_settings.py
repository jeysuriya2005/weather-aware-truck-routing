"""Settings for the automated test suite. Uses a throwaway, non-secret key."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-insecure-key")

from .settings import *  # noqa: E402,F401,F403
from .settings import REST_FRAMEWORK  # noqa: E402

# Tests must never depend on a real key or on .env contents.
TOMTOM_API_KEY = "test-tomtom-key-not-real"

# Tests call endpoints many times; throttling has its own dedicated test.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {"geocode": "10000/min", "trip_plan": "10000/min"},
}
