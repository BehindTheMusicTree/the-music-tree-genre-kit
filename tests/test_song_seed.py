import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from tests.fixture_app.models import Criteria, CriteriaPlaylist, Track
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


def test_import_songs_creates_tracks_from_payload(api_client, user, genres):
    payload = [
        {
            "title": "Strings of Life",
            "artist": "Derrick May",
            "youtube_video_id": "abc12345678",
            "genre_name": "Techno",
        },
        {"title": "Your Love", "artist": "Frankie Knuckles", "youtube_video_id": "xyz98765432", "genre_name": "House"},
    ]

    response = api_client.post("/tracks/songs/import/", data=payload, format="json")

    assert response.status_code == 201
    assert response.data == {"imported": 2, "skipped": 0}
    titles = set(Track.objects.filter(user=user).values_list("title", flat=True))
    assert titles == {"Strings of Life", "Your Love"}


def test_import_songs_reports_skipped_entries(api_client, user, genres):
    payload = [
        {"title": "Your Love", "artist": "Frankie Knuckles", "youtube_video_id": "xyz98765432", "genre_name": "House"},
        {"title": "No Genre", "artist": "Nobody", "youtube_video_id": "novideoid1", "genre_name": "Nonexistent"},
    ]

    response = api_client.post("/tracks/songs/import/", data=payload, format="json")

    assert response.status_code == 201
    assert response.data == {"imported": 1, "skipped": 1}


def test_import_songs_replaces_existing_tracks(api_client, user, genres):
    stale = Track.objects.create(user=user, title="Stale Track", genre=genres["House"])
    payload = [
        {"title": "Your Love", "artist": "Frankie Knuckles", "youtube_video_id": "xyz98765432", "genre_name": "House"}
    ]

    response = api_client.post("/tracks/songs/import/", data=payload, format="json")

    assert response.status_code == 201
    assert not Track.objects.filter(pk=stale.pk).exists()


def test_import_songs_rejects_invalid_payload(api_client, genres):
    payload = [{"title": "Missing Fields"}]

    response = api_client.post("/tracks/songs/import/", data=payload, format="json")

    assert response.status_code == 400
