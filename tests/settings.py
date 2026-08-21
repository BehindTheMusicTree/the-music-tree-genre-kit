from pathlib import Path

SECRET_KEY = "fixture-only-not-for-production"

DATA_DIR = Path(__file__).resolve().parent / "fixture_data"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "the_music_tree_api_kit",
    "the_music_tree_genre_kit",
    "tests.fixture_app",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

ROOT_URLCONF = "tests.urls"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CRITERIA_MODEL = "fixture_app.Criteria"
CRITERIA_NAME_LEN_MAX = 255
CRITERIA_TYPE_LABEL_LEN_MAX = 255
CRITERIA_TREE_IMPORT_MAX_TOTAL_COUNT = 500

PAGINATION_PAGE_SIZE_DEFAULT = 30
PAGINATION_PAGE_SIZE_MAX = 100
