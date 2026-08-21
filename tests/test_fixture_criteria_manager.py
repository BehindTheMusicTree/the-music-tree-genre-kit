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
def test_delete_instance_of_root_criteria_transfers_direct_tracks_and_clears_genre_and_reroots_children(
    user, genre_type, tag_type
):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)

    root_criteria = Criteria(user=user, type=genre_type)
    root_criteria._name = "root"
    root_criteria.save()

    child_criteria = Criteria(user=user, type=genre_type, parent=root_criteria)
    child_criteria._name = "child"
    child_criteria.save()

    CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=root_criteria)
    CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=child_criteria)

    genre_tagged_track = Track.objects.create(user=user, genre=root_criteria)
    direct_track = Track.objects.create(user=user)
    TrackPlaylistRel.objects.create(user=user, playlist=root_criteria.criteria_playlist, track=direct_track)

    Criteria.objects.delete_instance(root_criteria)

    genre_tagged_track.refresh_from_db()
    assert genre_tagged_track.genre is None

    genreless_playlist = CriteriaPlaylist.objects.get(user=user, criteria=None, type=genre_type)
    assert TrackPlaylistRel.objects.filter(playlist=genreless_playlist, track=direct_track).exists()

    child_playlist = CriteriaPlaylist.objects.get(criteria=child_criteria)
    assert child_playlist.is_root
