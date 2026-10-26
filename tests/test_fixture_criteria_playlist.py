import pytest
from django.contrib.auth import get_user_model

from tests.fixture_app.models import Criteria, CriteriaPlaylist, Track, TrackPlaylistRel
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


@pytest.mark.django_db
def test_criteria_playlist_root_and_parent_propagation(user, genre_type):
    root_criteria = Criteria(user=user, type=genre_type)
    root_criteria._name = "root"
    root_criteria.save()

    child_criteria = Criteria(user=user, type=genre_type, parent=root_criteria)
    child_criteria._name = "child"
    child_criteria.save()

    root_playlist = CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=root_criteria)
    child_playlist = CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=child_criteria)

    assert root_playlist.is_root
    assert child_playlist.parent == root_playlist
    assert child_playlist.root == root_playlist
    assert child_playlist.name == "child"


@pytest.mark.django_db
def test_criterialess_playlist_name_when_no_criteria(user, genre_type, tag_type):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)

    genreless = CriteriaPlaylist.objects.get(user=user, criteria=None, type=genre_type)
    tagless = CriteriaPlaylist.objects.get(user=user, criteria=None, type=tag_type)

    assert genreless.name == genreless.name_when_no_criteria
    assert tagless.name == tagless.name_when_no_criteria

    # Regression: bootstrap must be idempotent so it's safe to call from both a
    # post_save signal on new users and a one-off backfill for existing ones.
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    assert CriteriaPlaylist.objects.filter(user=user, criteria=None, type=genre_type).count() == 1


@pytest.mark.django_db
def test_transfer_direct_tracks_to_criterialess_playlist(user, genre_type, tag_type):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)

    root_criteria = Criteria(user=user, type=genre_type)
    root_criteria._name = "root"
    root_criteria.save()
    root_playlist = CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=root_criteria)

    track = Track.objects.create(user=user)
    TrackPlaylistRel.objects.create(user=user, playlist=root_playlist, track=track)

    # This is the bug fix under test: deleting a root Genre/Tag used to raise
    # CriteriaPlaylist.DoesNotExist because nothing ever created the criteria-less
    # catch-all row. With the bootstrap above in place, this must now succeed.
    CriteriaPlaylist.objects.transfer_direct_tracks_to_criterialess_playlist(
        direct_tracks=Track.objects.filter(pk=track.pk), criteria_playlist=root_playlist
    )

    genreless_playlist = CriteriaPlaylist.objects.get(user=user, criteria=None, type=genre_type)
    assert TrackPlaylistRel.objects.filter(playlist=genreless_playlist, track=track).exists()
    assert not TrackPlaylistRel.objects.filter(playlist=root_playlist, track=track).exists()


@pytest.mark.django_db
def test_transfer_direct_tracks_skips_tracks_already_in_criterialess_playlist(user, genre_type, tag_type):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    genreless_playlist = CriteriaPlaylist.objects.get(user=user, criteria=None, type=genre_type)

    root_criteria = Criteria(user=user, type=genre_type)
    root_criteria._name = "root"
    root_criteria.save()
    root_playlist = CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=root_criteria)

    track = Track.objects.create(user=user)
    assert TrackPlaylistRel.objects.filter(playlist=genreless_playlist, track=track).exists()
    TrackPlaylistRel.objects.create(user=user, playlist=root_playlist, track=track)

    CriteriaPlaylist.objects.transfer_direct_tracks_to_criterialess_playlist(
        direct_tracks=Track.objects.filter(pk=track.pk), criteria_playlist=root_playlist
    )

    assert TrackPlaylistRel.objects.filter(playlist=genreless_playlist, track=track).count() == 1
    assert not TrackPlaylistRel.objects.filter(playlist=root_playlist, track=track).exists()


@pytest.fixture
def bootstrapped(user, genre_type, tag_type):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)


def _playlist(user, genre_type, name):
    criteria = Criteria(user=user, type=genre_type)
    criteria._name = name
    criteria.save()
    return CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=criteria)


def _positions(playlist):
    return list(
        TrackPlaylistRel.objects.filter(playlist=playlist).order_by("position").values_list("track__title", "position")
    )


@pytest.mark.django_db
def test_bulk_prepend_track_rels_matches_per_track_creation(user, genre_type, bootstrapped):
    tracks = [Track.objects.create(user=user, title=f"t{i}") for i in range(5)]
    manager = CriteriaPlaylist.objects

    looped = _playlist(user, genre_type, "looped")
    bulk = _playlist(user, genre_type, "bulk")
    for playlist in (looped, bulk):
        TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=tracks[0])

    for track in tracks[1:]:
        manager._create_track_rel(user=user, playlist=looped, track=track)
    manager._bulk_prepend_track_rels(user=user, playlist=bulk, tracks=tracks[1:])

    assert _positions(bulk) == _positions(looped)
    assert [position for _, position in _positions(bulk)] == [1, 2, 3, 4, 5]


@pytest.mark.django_db
def test_bulk_prepend_track_rels_skips_tracks_already_in_playlist(user, genre_type, bootstrapped):
    tracks = [Track.objects.create(user=user, title=f"t{i}") for i in range(3)]
    playlist = _playlist(user, genre_type, "target")
    TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=tracks[0])

    CriteriaPlaylist.objects._bulk_prepend_track_rels(user=user, playlist=playlist, tracks=tracks)

    assert sorted(position for _, position in _positions(playlist)) == [1, 2, 3]
    assert TrackPlaylistRel.objects.filter(playlist=playlist, track=tracks[0]).count() == 1


@pytest.mark.django_db
def test_bulk_prepend_track_rels_query_count_is_independent_of_size(
    user, genre_type, bootstrapped, django_assert_max_num_queries
):
    tracks = [Track.objects.create(user=user, title=f"t{i}") for i in range(30)]
    playlist = _playlist(user, genre_type, "target")
    TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=tracks[0])

    with django_assert_max_num_queries(5):
        CriteriaPlaylist.objects._bulk_prepend_track_rels(user=user, playlist=playlist, tracks=tracks[1:])


@pytest.mark.django_db
def test_update_positions_to_fill_deleted_ones_compacts_with_constant_queries(
    user, genre_type, bootstrapped, django_assert_max_num_queries
):
    playlist = _playlist(user, genre_type, "target")
    for position in (2, 5, 6, 9):
        TrackPlaylistRel.objects.bulk_create(
            [TrackPlaylistRel(user=user, playlist=playlist, track=Track.objects.create(user=user), position=position)]
        )

    with django_assert_max_num_queries(3):
        TrackPlaylistRel.objects.update_positions_to_fill_deleted_ones(playlist)

    assert sorted(TrackPlaylistRel.objects.filter(playlist=playlist).values_list("position", flat=True)) == [1, 2, 3, 4]


@pytest.mark.django_db
def test_move_tracks_to_playlist_beginning_keeps_order_with_constant_queries(
    user, genre_type, bootstrapped, django_assert_max_num_queries
):
    source = _playlist(user, genre_type, "source")
    target = _playlist(user, genre_type, "target")
    existing = Track.objects.create(user=user, title="existing")
    TrackPlaylistRel.objects.bulk_create([TrackPlaylistRel(user=user, playlist=target, track=existing, position=1)])
    for position, title in enumerate(("a", "b", "c"), 1):
        track = Track.objects.create(user=user, title=title)
        TrackPlaylistRel.objects.bulk_create(
            [TrackPlaylistRel(user=user, playlist=source, track=track, position=position)]
        )

    with django_assert_max_num_queries(6):
        TrackPlaylistRel.objects.move_tracks_to_playlist_beginning(
            source_rels=TrackPlaylistRel.objects.filter(playlist=source), target_playlist=target
        )

    assert _positions(target) == [("a", 1), ("b", 2), ("c", 3), ("existing", 4)]
    assert not TrackPlaylistRel.objects.filter(playlist=source).exists()
