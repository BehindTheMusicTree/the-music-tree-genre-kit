import pytest
from django.contrib.auth import get_user_model

from tests.fixture_app.models import Criteria, CriteriaPlaylist, ManualPlaylist, Track
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks
from the_music_tree_genre_kit.playlist.Playlist import Playlist as KitPlaylist
from the_music_tree_genre_kit.playlist.PlaylistTypesLabel import PlaylistTypesLabel


@pytest.fixture
def user():
    return get_user_model().objects.create(username="fixture-user")


@pytest.fixture
def genre_type():
    return CriteriaType.objects.create(pk=int(CriteriaTypePks.GENRE), label="genre")


@pytest.mark.django_db
def test_manual_playlist_type_label_and_name(user):
    manual_playlist = ManualPlaylist(user=user)
    manual_playlist._name = "My Mix"
    manual_playlist.save()

    assert manual_playlist.playlist.name == "My Mix"
    assert manual_playlist.playlist.type_label == PlaylistTypesLabel.MANUAL


@pytest.mark.django_db
def test_criteria_playlist_type_label_and_name(user, genre_type):
    root_criteria = Criteria(user=user, type=genre_type)
    root_criteria._name = "root"
    root_criteria.save()

    criteria_playlist = CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=root_criteria)

    assert criteria_playlist.playlist.name == "root"
    assert criteria_playlist.playlist.type_label == PlaylistTypesLabel.GENRE


@pytest.mark.django_db
def test_playlist_name_and_type_label_raise_without_manual_or_criteria_playlist(user):
    playlist = KitPlaylist.objects.create(user=user)

    with pytest.raises(ValueError, match="has no name"):
        _ = playlist.name
    with pytest.raises(ValueError, match="has no type"):
        _ = playlist.type_label


@pytest.mark.django_db
def test_tracks_not_archived_dict_by_position(user, genre_type):
    root_criteria = Criteria(user=user, type=genre_type)
    root_criteria._name = "root"
    root_criteria.save()
    criteria_playlist = CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=root_criteria)
    playlist = criteria_playlist.playlist

    track_a = Track.objects.create(user=user, genre=root_criteria)
    track_b = Track.objects.create(user=user, genre=root_criteria)

    result = playlist.tracks_not_archived_dict_by_position

    # Each create shifts existing relations to position+1 and takes position 1 itself.
    # `.track` resolves through the kit's base `Track` model (MTI parent), not the
    # fixture app's concrete subclass, so compare by pk rather than instance equality.
    assert {position: track.pk for position, track in result.items()} == {1: track_b.pk, 2: track_a.pk}


@pytest.mark.django_db
def test_tracks_not_archived_dict_by_position_empty_when_no_relations(user, genre_type):
    root_criteria = Criteria(user=user, type=genre_type)
    root_criteria._name = "root"
    root_criteria.save()
    criteria_playlist = CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=root_criteria)

    assert criteria_playlist.playlist.tracks_not_archived_dict_by_position == {}
