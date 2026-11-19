"""Full-suite PostgreSQL settings: same fixture_app as SQLite, only the database differs.

Credentials must identify a disposable test database.
"""

import os

from tests.settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRES_TEST_DATABASE"],
        "USER": os.environ["POSTGRES_TEST_USER"],
        "HOST": os.environ["POSTGRES_TEST_HOST"],
        "PORT": os.environ["POSTGRES_TEST_PORT"],
    }
}
