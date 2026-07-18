from __future__ import annotations

SECRET_KEY = "not-a-secret-test-key"
DEBUG = True
USE_TZ = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "fiction_scout.adapters.django",
    "tests.django_app",
]

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
