"""Opt-in concurrency checks; credentials must identify a disposable test database."""

import os

from tests.settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["GENRE_GRAPH_TEST_DATABASE"],
        "USER": os.environ["GENRE_GRAPH_TEST_USER"],
        "HOST": os.environ["GENRE_GRAPH_TEST_HOST"],
        "PORT": os.environ["GENRE_GRAPH_TEST_PORT"],
    }
}

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "tests.fixture_app"] + ["tests.graph_storage_app"]  # noqa: F405
CRITERIA_MODEL = "graph_storage_app.Criteria"
ARTIST_MODEL = "graph_storage_app.Artist"
ALBUM_MODEL = "graph_storage_app.Album"
TRACK_MODEL = "the_music_tree_genre_kit.Track"
ROOT_URLCONF = "tests.graph_storage_app.urls"
