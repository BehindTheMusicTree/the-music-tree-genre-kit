import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from tests.fixture_app.models import Criteria, CriteriaPlaylist, Track
from tests.fixture_app.viewset import TrackViewSet
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks


@pytest.fixture
def user(db):
    return get_user_model().objects.create(username="fixture-user")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def genre_type(db):
    return CriteriaType.objects.create(pk=int(CriteriaTypePks.GENRE), label="genre")


@pytest.fixture
def genres(user, genre_type):
    created = {}
    for name in ("Techno", "House"):
        criteria = Criteria(user=user, type=genre_type)
        criteria._name = name
        criteria.save()
        CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=criteria)
        created[name] = criteria
    return created


def test_load_example_songs_creates_tracks_from_fixture(api_client, user, genres):
    response = api_client.post("/tracks/songs/load-example/")

    assert response.status_code == 201
    titles = set(Track.objects.filter(user=user).values_list("title", flat=True))
    assert titles == {"Strings of Life", "Your Love"}


def test_load_example_songs_replaces_existing_tracks(api_client, user, genres):
    stale = Track.objects.create(user=user, title="Stale Track", genre=genres["House"])

    response = api_client.post("/tracks/songs/load-example/")

    assert response.status_code == 201
    assert not Track.objects.filter(pk=stale.pk).exists()


def test_load_example_songs_missing_file_raises(api_client, genres, settings, tmp_path):
    settings.DATA_DIR = tmp_path

    with pytest.raises(FileNotFoundError):
        api_client.post("/tracks/songs/load-example/")


def test_load_example_songs_calls_on_loaded_hook(api_client, user, genres, monkeypatch):
    calls = []

    monkeypatch.setattr(TrackViewSet, "on_example_songs_loaded", lambda self, request: calls.append(request.user))

    response = api_client.post("/tracks/songs/load-example/")

    assert response.status_code == 201
    assert calls == [user]
