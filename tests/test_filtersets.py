from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException

from tests.fixture_app.models import Criteria, CriteriaPlaylist, ManualPlaylist
from the_music_tree_genre_kit.criteria.playlist.bootstrap_criterialess_playlists_for_user import (
    bootstrap_criterialess_playlists_for_user,
)
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks
from the_music_tree_genre_kit.filtering.set.criteria.CriteriaFilterSet import CriteriaFilterSet
from the_music_tree_genre_kit.filtering.set.criteria_playlist.CriteriaPlaylistFilterSet import (
    CriteriaPlaylistFilterSet,
)
from the_music_tree_genre_kit.filtering.set.manual_playlist.ManualPlaylistFilterSet import ManualPlaylistFilterSet
from the_music_tree_genre_kit.filtering.set.playlist.PlaylistFilterSet import PlaylistFilterSet
from the_music_tree_genre_kit.playlist.Playlist import Playlist


@pytest.fixture
def user(db):
    user = get_user_model().objects.create(username="fixture-user")
    CriteriaType.objects.create(pk=int(CriteriaTypePks.GENRE), label="genre")
    CriteriaType.objects.create(pk=int(CriteriaTypePks.TAG), label="tag")
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    return user


def _criteria(user, name, parent=None):
    criteria = Criteria(user=user, type_id=int(CriteriaTypePks.GENRE), parent=parent)
    criteria._name = name
    criteria.save()
    CriteriaPlaylist.objects.create(user=user, type_id=int(CriteriaTypePks.GENRE), criteria=criteria)
    return criteria


def _manual(user, name):
    playlist = ManualPlaylist(user=user)
    playlist._name = name
    playlist.save()
    return playlist


def _qs(filterset_class, queryset, data):
    return filterset_class(data=data, queryset=queryset, request=RequestFactory().get("/", data)).qs


def _names(filterset_class, queryset, **data):
    return {obj.name for obj in _qs(filterset_class, queryset, data)}


def _playlist_names(**data):
    return {
        (p.manual_playlist if hasattr(p, "manual_playlist") else p.criteria_playlist).name
        for p in _qs(PlaylistFilterSet, Playlist.objects.all(), data)
    }


def test_criteria_filterset_name_and_parent(user):
    fiesta = _criteria(user, "Fiesta")
    _criteria(user, "Punk", parent=fiesta)
    _criteria(user, "Pop")

    assert _names(CriteriaFilterSet, Criteria.objects.all(), name="pu") == {"Punk"}
    assert _names(CriteriaFilterSet, Criteria.objects.all(), parent=str(fiesta.pk)) == {"Punk"}


def test_criteria_filterset_rejects_blank_name(user):
    with pytest.raises(AppValidationException):
        _qs(CriteriaFilterSet, Criteria.objects.all(), {"name": ""})


def test_criteria_playlist_filterset_name_parent_and_updated_on_range(user):
    now = timezone.now()
    past = now - timedelta(days=5)
    fiesta = _criteria(user, "Fiesta")
    for name, updated_on in [("Summer", now), ("Winter", past - timedelta(days=1)), ("Spring", now)]:
        CriteriaPlaylist.objects.filter(criteria=_criteria(user, name, parent=fiesta)).update(updated_on=updated_on)
    _criteria(user, "Beach")

    names = _names(
        CriteriaPlaylistFilterSet,
        CriteriaPlaylist.objects.all(),
        name="s",
        parent=str(fiesta.criteria_playlist.pk),
        updated_on_gte=past.isoformat(),
        updated_on_lte=(now + timedelta(days=2)).isoformat(),
    )

    assert names == {"Summer", "Spring"}


def test_criteria_playlist_filterset_name_matches_criterialess_playlist(user):
    _criteria(user, "Genre music")

    assert _names(CriteriaPlaylistFilterSet, CriteriaPlaylist.objects.all(), name="genre") == {
        "Genreless",
        "Genre music",
    }


def test_criteria_playlist_filterset_canonical_tree_includes_criterialess(user):
    _criteria(user, "Rock")

    assert _names(CriteriaPlaylistFilterSet, CriteriaPlaylist.objects.all(), tree_name="canonical") == {
        "Genreless",
        "Tagless",
        "Rock",
    }


def test_manual_playlist_filterset_name(user):
    _manual(user, "Road trip")
    _manual(user, "Workout")

    assert _names(ManualPlaylistFilterSet, ManualPlaylist.objects.all(), name="road") == {"Road trip"}


def test_playlist_filterset_name_and_type(user):
    _manual(user, "Rock mix")
    _criteria(user, "Rock")

    assert _playlist_names(name="rock") == {"Rock mix", "Rock"}
    assert _playlist_names(name="rock", type="genre") == {"Rock"}
    assert _playlist_names(name="less", type="tag") == {"Tagless"}
