SECRET_KEY = "fixture-only-not-for-production"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
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

USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CRITERIA_NAME_LEN_MAX = 255
CRITERIA_TYPE_LABEL_LEN_MAX = 255
CRITERIA_TREE_IMPORT_MAX_TOTAL_COUNT = 500
