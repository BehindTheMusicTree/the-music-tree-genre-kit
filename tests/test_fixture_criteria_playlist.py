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
def test_archive_and_unarchive_instances_of_track(user, genre_type):
    root_criteria = Criteria(user=user, type=genre_type)
    root_criteria._name = "root"
    root_criteria.save()
    playlist = CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=root_criteria)

    track_a = Track.objects.create(user=user)
    track_b = Track.objects.create(user=user)
    TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=track_a)
    TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=track_b)

    TrackPlaylistRel.objects.archive_instances_of_track(track_b)
    rel_a = TrackPlaylistRel.objects.get(playlist=playlist, track=track_a)
    rel_b = TrackPlaylistRel.objects.get(playlist=playlist, track=track_b)
    assert rel_b.position is None
    assert rel_a.position == 1

    TrackPlaylistRel.objects.unarchive_instances_of_track(track_b)
    rel_a.refresh_from_db()
    rel_b.refresh_from_db()
    assert rel_b.position == 1
    assert rel_a.position == 2
