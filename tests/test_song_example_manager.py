import pytest
from django.contrib.auth import get_user_model

from tests.fixture_app.models import Artist, Criteria, CriteriaPlaylist, Track, TrackPlaylistRel
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


@pytest.fixture
def deep_house(user, genre_type, tag_type):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)

    electronic = Criteria(user=user, type=genre_type)
    electronic._name = "Electronic"
    electronic.save()
    CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=electronic)

    house = Criteria(user=user, type=genre_type, parent=electronic)
    house._name = "House"
    house.save()
    CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=house)

    deep_house = Criteria(user=user, type=genre_type, parent=house)
    deep_house._name = "Deep House"
    deep_house.save()
    CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=deep_house)

    return electronic, house, deep_house


@pytest.mark.django_db
def test_import_example_songs_adds_multi_level_ancestor_playlist_rels(user, deep_house):
    electronic, house, deep_house_genre = deep_house

    Track.objects.import_example_songs(
        user,
        [
            {
                "title": "Silent Shout",
                "artist": "The Knife",
                "youtube_video_id": "aaa111",
                "genre_name": "Deep House",
            }
        ],
    )

    track = Track.objects.get(user=user, title="Silent Shout")

    assert TrackPlaylistRel.objects.filter(playlist=deep_house_genre.criteria_playlist, track=track).exists()
    assert TrackPlaylistRel.objects.filter(playlist=house.criteria_playlist, track=track).exists()
    assert TrackPlaylistRel.objects.filter(playlist=electronic.criteria_playlist, track=track).exists()


@pytest.mark.django_db
def test_import_example_songs_orders_playlist_rels_most_recent_first(user, deep_house):
    _electronic, house, deep_house_genre = deep_house

    Track.objects.import_example_songs(
        user,
        [
            {"title": "First", "artist": "Artist A", "youtube_video_id": "id1", "genre_name": "House"},
            {"title": "Second", "artist": "Artist B", "youtube_video_id": "id2", "genre_name": "Deep House"},
        ],
    )

    first_track = Track.objects.get(user=user, title="First")
    second_track = Track.objects.get(user=user, title="Second")

    first_rel = TrackPlaylistRel.objects.get(playlist=house.criteria_playlist, track=first_track)
    second_rel = TrackPlaylistRel.objects.get(playlist=house.criteria_playlist, track=second_track)

    # Later-processed entries land on top, mirroring the per-row `create()` LIFO shift.
    assert second_rel.position < first_rel.position
    assert not TrackPlaylistRel.objects.filter(playlist=deep_house_genre.criteria_playlist, track=first_track).exists()


@pytest.mark.django_db
def test_import_example_songs_large_batch(user, deep_house):
    electronic, house, deep_house_genre = deep_house

    entry_count = 300
    data = [
        {
            "title": f"Track {index}",
            "artist": f"Artist {index % 25}",
            "youtube_video_id": f"vid{index}",
            "genre_name": "Deep House" if index % 3 == 0 else ("House" if index % 3 == 1 else "Electronic"),
        }
        for index in range(entry_count)
    ]
    # A handful of unmatched entries mixed in should still be skipped.
    data.append(
        {"title": "Unmatched", "artist": "Nobody", "youtube_video_id": "novid", "genre_name": "Not A Real Genre"}
    )

    Track.objects.import_example_songs(user, data)

    assert Track.objects.filter(user=user).count() == entry_count
    assert not Track.objects.filter(user=user, title="Unmatched").exists()
    assert Artist.objects.filter(user=user).count() == 25

    deep_house_count = sum(1 for index in range(entry_count) if index % 3 == 0)
    house_count = sum(1 for index in range(entry_count) if index % 3 == 1)
    electronic_count = sum(1 for index in range(entry_count) if index % 3 == 2)

    assert TrackPlaylistRel.objects.filter(playlist=deep_house_genre.criteria_playlist).count() == deep_house_count
    # `house`'s playlist gets its own direct entries plus every deep-house descendant.
    assert TrackPlaylistRel.objects.filter(playlist=house.criteria_playlist).count() == house_count + deep_house_count
    assert (
        TrackPlaylistRel.objects.filter(playlist=electronic.criteria_playlist).count()
        == electronic_count + house_count + deep_house_count
    )
