import pytest
from django.contrib.auth import get_user_model

from tests.fixture_app.models import Artist, Criteria, CriteriaPlaylist, Track
from the_music_tree_genre_kit.criteria.playlist.bootstrap_criterialess_playlists_for_user import (
    bootstrap_criterialess_playlists_for_user,
)
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks


@pytest.fixture
def user():
    return get_user_model().objects.create(username="fixture-user")


@pytest.fixture
def genre_type():
    return CriteriaType.objects.create(pk=int(CriteriaTypePks.GENRE), label="genre")


@pytest.fixture
def tag_type():
    return CriteriaType.objects.create(pk=int(CriteriaTypePks.TAG), label="tag")


@pytest.fixture
def house(user, genre_type, tag_type):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)

    house = Criteria(user=user, type=genre_type)
    house._name = "House"
    house.save()
    CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=house)
    return house


@pytest.mark.django_db
def test_import_example_songs_creates_track_for_matching_genre(user, house):
    Track.objects.import_example_songs(
        user,
        [{"title": "Your Love", "artist": "Frankie Knuckles", "youtube_video_id": "abc123", "genre_name": "house"}],
    )

    track = Track.objects.get(user=user, title="Your Love")
    assert track.genre_id == house.pk
    assert track.youtube_video_id == "abc123"
    assert list(track.artists.values_list("name", flat=True)) == ["Frankie Knuckles"]


@pytest.mark.django_db
def test_import_example_songs_skips_entry_with_no_matching_genre(user, house):
    Track.objects.import_example_songs(
        user,
        [
            {
                "title": "No Genre Song",
                "artist": "Nobody",
                "youtube_video_id": "xyz789",
                "genre_name": "Nonexistent Genre",
            }
        ],
    )

    assert not Track.objects.filter(user=user, title="No Genre Song").exists()


@pytest.mark.django_db
def test_import_example_songs_reuses_existing_artist(user, house):
    existing_artist = Artist.objects.create(user=user, name="Frankie Knuckles")

    Track.objects.import_example_songs(
        user,
        [{"title": "Your Love", "artist": "Frankie Knuckles", "youtube_video_id": "abc123", "genre_name": "House"}],
    )

    track = Track.objects.get(user=user, title="Your Love")
    assert list(track.artists.all()) == [existing_artist]
    assert Artist.objects.filter(user=user, name="Frankie Knuckles").count() == 1


@pytest.mark.django_db
def test_import_example_songs_replaces_existing_tracks(user, house):
    stale = Track.objects.create(user=user, title="Stale Track")

    Track.objects.import_example_songs(
        user,
        [{"title": "Your Love", "artist": "Frankie Knuckles", "youtube_video_id": "abc123", "genre_name": "House"}],
    )

    assert not Track.objects.filter(pk=stale.pk).exists()
    assert Track.objects.filter(user=user).count() == 1
