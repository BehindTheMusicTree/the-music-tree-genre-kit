import pytest
from django.contrib.auth import get_user_model

from tests.fixture_app.models import Criteria, CriteriaPlaylist, ManualPlaylist
from the_music_tree_genre_kit.criteria.playlist.bootstrap_criterialess_playlists_for_user import (
    bootstrap_criterialess_playlists_for_user,
)
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks
from the_music_tree_genre_kit.playlist.Playlist import Playlist as KitPlaylist


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
def playlists(user, genre_type, tag_type):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)

    genre_criteria = Criteria(user=user, type=genre_type)
    genre_criteria._name = "House"
    genre_criteria.save()
    genre_playlist = CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=genre_criteria)

    tag_criteria = Criteria(user=user, type=tag_type)
    tag_criteria._name = "Favorites"
    tag_criteria.save()
    tag_playlist = CriteriaPlaylist.objects.create(user=user, type=tag_type, criteria=tag_criteria)

    manual_playlist = ManualPlaylist(user=user)
    manual_playlist._name = "My House Mix"
    manual_playlist.save()

    return {
        "genre": genre_playlist.playlist,
        "tag": tag_playlist.playlist,
        "manual": manual_playlist.playlist,
    }


@pytest.mark.django_db
def test_filter_without_type_or_name_returns_plain_queryset(user, playlists):
    result = KitPlaylist.objects.filter(user=user)

    assert set(result) >= {playlists["genre"], playlists["tag"], playlists["manual"]}


@pytest.mark.django_db
def test_filter_by_manual_type_label(user, playlists):
    result = KitPlaylist.objects.filter(user=user, type="manual", name="")

    assert list(result) == [playlists["manual"]]


@pytest.mark.django_db
def test_filter_by_genre_type_label_and_name(user, playlists):
    result = KitPlaylist.objects.filter(user=user, type="genre", name="House")

    assert list(result) == [playlists["genre"]]


@pytest.mark.django_db
def test_filter_by_tag_type_label_excludes_genre(user, playlists):
    result = KitPlaylist.objects.filter(user=user, type="tag", name="")

    assert playlists["tag"] in result
    assert playlists["genre"] not in result
    assert playlists["manual"] not in result


@pytest.mark.django_db
def test_filter_by_name_only_matches_across_types(user, playlists):
    result = KitPlaylist.objects.filter(user=user, name="House")

    assert playlists["genre"] in result
    assert playlists["manual"] in result
    assert playlists["tag"] not in result


@pytest.mark.django_db
def test_filter_by_name_matching_genreless_playlist(user, playlists, genre_type):
    genreless = CriteriaPlaylist.objects.get(user=user, criteria=None, type=genre_type)

    result = KitPlaylist.objects.filter(user=user, type="genre", name="Genreless")

    assert genreless.playlist in result
    assert playlists["genre"] not in result
