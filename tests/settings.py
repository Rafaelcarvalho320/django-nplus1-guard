"""Minimal Django settings for the test suite."""

SECRET_KEY = "test-only"
DEBUG = False

DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "tests.testapp",
]

MIDDLEWARE = ["nplus1_guard.middleware.NPlusOneMiddleware"]

ROOT_URLCONF = "tests.urls"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

NPLUS1_GUARD = {"ENABLED": True, "THRESHOLD": 3}
