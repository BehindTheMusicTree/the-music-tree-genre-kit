import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

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
def test_import_seed_songs_creates_track_for_matching_genre(user, house):
    result = Track.objects.import_seed_songs(
        user,
        [{"title": "Your Love", "artist": "Frankie Knuckles", "youtube_video_id": "abc123", "genre_name": "house"}],
    )

    track = Track.objects.get(user=user, title="Your Love")
    assert track.genre_id == house.pk
    assert track.youtube_video_id == "abc123"
    assert list(track.artists.values_list("name", flat=True)) == ["Frankie Knuckles"]
    assert result == {"imported": 1, "skipped": 0}


@pytest.mark.django_db
def test_import_seed_songs_skips_entry_with_no_matching_genre(user, house):
    result = Track.objects.import_seed_songs(
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
    assert result == {"imported": 0, "skipped": 1}


@pytest.mark.django_db
def test_import_seed_songs_reuses_existing_artist(user, house):
    existing_artist = Artist.objects.create(user=user, name="Frankie Knuckles")

    Track.objects.import_seed_songs(
        user,
        [{"title": "Your Love", "artist": "Frankie Knuckles", "youtube_video_id": "abc123", "genre_name": "House"}],
    )

    track = Track.objects.get(user=user, title="Your Love")
    assert list(track.artists.all()) == [existing_artist]
    assert Artist.objects.filter(user=user, name="Frankie Knuckles").count() == 1


@pytest.mark.django_db
def test_import_seed_songs_replaces_existing_tracks(user, house):
    stale = Track.objects.create(user=user, title="Stale Track")

    Track.objects.import_seed_songs(
        user,
        [{"title": "Your Love", "artist": "Frankie Knuckles", "youtube_video_id": "abc123", "genre_name": "House"}],
    )

    assert not Track.objects.filter(pk=stale.pk).exists()
    assert Track.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_import_seed_songs_upserts_matching_video_id_instead_of_recreating(user, house):
    existing = Track.objects.create(user=user, title="Old Title", genre=house, youtube_video_id="abc123")

    result = Track.objects.import_seed_songs(
        user,
        [{"title": "New Title", "artist": "Frankie Knuckles", "youtube_video_id": "abc123", "genre_name": "House"}],
    )

    existing.refresh_from_db()
    assert existing.title == "New Title"
    assert Track.objects.filter(user=user).count() == 1
    assert result == {"imported": 1, "skipped": 0}


@pytest.mark.django_db
def test_import_seed_songs_locked_track_keeps_its_genre(user, house):
    other = Criteria(user=user, type=house.type)
    other._name = "Techno"
    other.save()
    CriteriaPlaylist.objects.create(user=user, type=house.type, criteria=other)

    locked = Track.objects.create(
        user=user, title="Locked Song", genre=other, youtube_video_id="abc123", is_manually_edited=True
    )

    Track.objects.import_seed_songs(
        user,
        [{"title": "Locked Song", "artist": "Someone", "youtube_video_id": "abc123", "genre_name": "House"}],
    )

    locked.refresh_from_db()
    assert locked.genre_id == other.pk
    assert locked.title == "Locked Song"


@pytest.mark.django_db
def test_import_seed_songs_never_deletes_locked_track_even_when_absent(user, house):
    locked = Track.objects.create(user=user, title="Locked Song", youtube_video_id="abc123", is_manually_edited=True)

    Track.objects.import_seed_songs(
        user,
        [{"title": "Other Song", "artist": "Someone", "youtube_video_id": "zzz999", "genre_name": "House"}],
    )

    assert Track.objects.filter(pk=locked.pk).exists()


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
def test_import_seed_songs_adds_multi_level_ancestor_playlist_rels(user, deep_house):
    electronic, house, deep_house_genre = deep_house

    Track.objects.import_seed_songs(
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
def test_import_seed_songs_orders_playlist_rels_most_recent_first(user, deep_house):
    _electronic, house, deep_house_genre = deep_house

    Track.objects.import_seed_songs(
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
def test_import_seed_songs_large_batch(user, deep_house):
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

    # The `artists` M2M write is a single `bulk_create` against its auto-generated through
    # table, not one query per song - asserting exactly one query touches that table is a
    # regression guard against it turning back into a per-song `.set()` loop. (The overall
    # query count still scales with `entry_count`: `Track.save()` can't be `bulk_create`d, a
    # known multi-table-inheritance ceiling, not something this fix addresses.)
    with CaptureQueriesContext(connection) as queries:
        Track.objects.import_seed_songs(user, data)
    through_table = Track.artists.through._meta.db_table
    through_queries = [q for q in queries.captured_queries if through_table in q["sql"]]
    assert len(through_queries) == 1

    assert Track.objects.filter(user=user).count() == entry_count
    assert not Track.objects.filter(user=user, title="Unmatched").exists()
    assert Artist.objects.filter(user=user).count() == 25

    for track in Track.objects.filter(user=user).select_related(None).prefetch_related("artists"):
        index = int(track.title.removeprefix("Track "))
        assert [artist.name for artist in track.artists.all()] == [f"Artist {index % 25}"]

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
