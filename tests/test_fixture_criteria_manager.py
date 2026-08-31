import pytest
from django.contrib.auth import get_user_model
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException

from tests.fixture_app.models import Criteria, CriteriaPlaylist, Genre, Track, TrackPlaylistRel
from the_music_tree_genre_kit.criteria.CriteriaSide import CriteriaSide
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


@pytest.mark.django_db
def test_side_is_not_a_field_on_plain_criteria(user, tag_type):
    tag = Criteria(user=user, type=tag_type)
    tag._name = "some-tag"
    tag.save()

    assert not hasattr(tag, "side")
    assert not any(field.name == "side" for field in Criteria._meta.get_fields())


@pytest.mark.django_db
def test_import_and_export_round_trip_preserves_pop_side(user, genre_type):
    tree_data = {
        "tree": [
            {
                "name": "Electronic",
                "children": [
                    {"name": "Core Electronic", "children": []},
                    {"name": "Pop Electronic", "side": "pop", "children": []},
                ],
            }
        ]
    }

    Genre.objects.import_criteria_tree(user, tree_data)

    pop_child = Genre.objects.get(user=user, _name="Pop Electronic")
    assert pop_child.side == CriteriaSide.POP

    core_child = Genre.objects.get(user=user, _name="Core Electronic")
    assert core_child.side is None

    exported = Genre.objects.build_criteria_tree(user)
    root_node = exported[0]
    exported_children_by_name = {child["name"]: child for child in root_node["children"]}

    assert exported_children_by_name["Pop Electronic"]["side"] == CriteriaSide.POP
    assert exported_children_by_name["Core Electronic"]["side"] is None


@pytest.mark.django_db
def test_import_root_with_only_core_child_keeps_side_null(user, genre_type):
    tree_data = {"tree": [{"name": "Classical", "children": [{"name": "Baroque", "children": []}]}]}

    Genre.objects.import_criteria_tree(user, tree_data)

    baroque = Genre.objects.get(user=user, _name="Baroque")
    assert baroque.side is None

    exported = Genre.objects.build_criteria_tree(user)
    assert exported[0]["children"][0]["side"] is None


@pytest.mark.django_db
def test_pop_side_on_non_root_child_raises(user, genre_type):
    root = Genre(user=user, type=genre_type)
    root._name = "root"
    root.save()

    child = Genre(user=user, type=genre_type, parent=root)
    child._name = "child"
    child.save()

    grandchild = Genre(user=user, type=genre_type, parent=child, side=CriteriaSide.POP)
    grandchild._name = "grandchild"

    with pytest.raises(AppValidationException):
        grandchild.save()


@pytest.mark.django_db
def test_second_pop_side_sibling_raises(user, genre_type):
    root = Genre(user=user, type=genre_type)
    root._name = "root"
    root.save()

    first_pop_child = Genre(user=user, type=genre_type, parent=root, side=CriteriaSide.POP)
    first_pop_child._name = "first-pop"
    first_pop_child.save()

    second_pop_child = Genre(user=user, type=genre_type, parent=root, side=CriteriaSide.POP)
    second_pop_child._name = "second-pop"

    with pytest.raises(AppValidationException):
        second_pop_child.save()
