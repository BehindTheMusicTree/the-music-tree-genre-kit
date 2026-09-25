import pytest
from django.contrib.auth import get_user_model
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException
from the_music_tree_api_kit.exception.validation.FieldValidationErrorCode import FieldValidationErrorCode

from tests.fixture_app.models import Criteria, CriteriaPlaylist, Genre, Track, TrackPlaylistRel
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
def make(user, genre_type, tag_type):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)

    def make(name, parent=None, criteria_type=genre_type, **kwargs):
        criteria = Criteria.objects.create(user=user, _name=name, parent=parent, **kwargs)
        if criteria.type_id != criteria_type.pk:
            criteria.type = criteria_type
            criteria.save(update_fields=["type"])
        CriteriaPlaylist.objects.create(user=user, type=criteria_type, criteria=criteria)
        return criteria

    return make


def playlist_has(criteria, track):
    return TrackPlaylistRel.objects.filter(playlist=criteria.criteria_playlist, track=track).exists()


def ascendant_names(criteria):
    return set(criteria.ascendants.values_list("_name", flat=True))


def error_code(callable_):
    with pytest.raises(AppValidationException) as exc_info:
        callable_()
    return exc_info.value.field_validation_error_code


@pytest.mark.django_db
def test_track_flows_into_every_primary_branch_but_not_secondary_parents(user, make):
    rock, jazz, pop = make("Rock"), make("Jazz"), make("Pop")
    fusion = make(
        "Fusion",
        parent=rock,
        allows_multiple_primary_parents=True,
        additional_primary_parents=[jazz],
        secondary_parents=[pop],
    )

    track = Track.objects.create(user=user, genre=fusion)

    assert ascendant_names(fusion) == {"Rock", "Jazz"}
    assert playlist_has(fusion, track) and playlist_has(rock, track) and playlist_has(jazz, track)
    assert not playlist_has(pop, track)

    Track.objects.update_instance(track, genre=rock)
    assert playlist_has(rock, track)
    assert not playlist_has(jazz, track) and not playlist_has(fusion, track)


@pytest.mark.django_db
def test_changing_primary_parents_moves_tracks_only_on_lost_paths(user, make):
    rock, jazz, blues = make("Rock"), make("Jazz"), make("Blues")
    fusion = make("Fusion", parent=rock, allows_multiple_primary_parents=True, additional_primary_parents=[jazz])
    track = Track.objects.create(user=user, genre=fusion)

    Criteria.objects.update_instance(fusion, additional_primary_parents=[blues])

    assert ascendant_names(fusion) == {"Rock", "Blues"}
    assert playlist_has(rock, track) and playlist_has(blues, track)
    assert not playlist_has(jazz, track)


@pytest.mark.django_db
def test_secondary_parent_on_tag_gets_no_ascendant(make, tag_type):
    mood = make("Mood", criteria_type=tag_type)
    chill = make("Chill", criteria_type=tag_type)
    Criteria.objects.update_instance(chill, secondary_parents=[mood])

    assert ascendant_names(chill) == set()
    assert list(mood.secondary_children.all()) == [chill]


@pytest.mark.django_db
def test_parent_invariants_are_enforced(make, tag_type):
    rock, jazz = make("Rock"), make("Jazz")
    mood = make("Mood", criteria_type=tag_type)
    fusion = make("Fusion", parent=rock, allows_multiple_primary_parents=True)

    assert (
        error_code(lambda: make("Plain", parent=rock, additional_primary_parents=[jazz]))
        == FieldValidationErrorCode.DEPENDENCY_MISSING
    )
    assert (
        error_code(lambda: make("Orphan", allows_multiple_primary_parents=True, additional_primary_parents=[jazz]))
        == FieldValidationErrorCode.DEPENDENCY_MISSING
    )
    assert error_code(lambda: make("Strict", parent=fusion)) == FieldValidationErrorCode.DEPENDENCY_MISSING
    assert error_code(lambda: make("Cross", secondary_parents=[mood])) == FieldValidationErrorCode.REFERENCE_INVALID
    assert (
        error_code(lambda: Criteria.objects.update_instance(jazz, secondary_parents=[jazz]))
        == FieldValidationErrorCode.SELF_REFERENCE
    )
    assert (
        error_code(lambda: Criteria.objects.update_instance(fusion, additional_primary_parents=[rock]))
        == FieldValidationErrorCode.DUPLICATE
    )
    assert (
        error_code(lambda: Criteria.objects.update_instance(rock, secondary_parents=[fusion]))
        == FieldValidationErrorCode.ANCESTOR_REFERENCE
    )


@pytest.mark.django_db
def test_deleting_main_parent_promotes_additional_primary_parent(user, make):
    rock, jazz = make("Rock"), make("Jazz")
    fusion = make("Fusion", parent=rock, allows_multiple_primary_parents=True, additional_primary_parents=[jazz])

    Criteria.objects.delete_instance(rock)

    fusion.refresh_from_db()
    assert fusion.parent == jazz and fusion.root == jazz
    assert list(fusion.additional_primary_parents.all()) == []
    assert ascendant_names(fusion) == {"Jazz"}


def import_tree(user, flag, tree):
    Genre.objects.import_criteria_tree(user, {"allows_multiple_primary_parents": flag, "tree": tree})


@pytest.mark.django_db
def test_import_scopes_by_flag_and_round_trips_parent_refs(user, genre_type):
    single_tree = [
        {"name": "Rock", "id": "Q11399", "children": [], "secondary_parents": ["Q8341"]},
        {"name": "Jazz", "id": "Q8341", "children": []},
    ]
    multi_tree = [
        {
            "name": "Fusion",
            "id": "Q1",
            "primary_parents": ["Q11399", "Jazz"],
            "children": [{"name": "Nu Fusion", "id": "Q2", "children": []}],
        }
    ]
    import_tree(user, False, single_tree)
    import_tree(user, True, multi_tree)
    import_tree(user, False, single_tree)

    fusion = Genre.objects.get(user=user, wikidata_id="Q1")
    nu_fusion = Genre.objects.get(user=user, wikidata_id="Q2")
    assert fusion.parent.name == "Rock" and nu_fusion.root_id == fusion.parent_id
    assert ascendant_names(nu_fusion) == {"Fusion", "Rock", "Jazz"}
    assert {rel.ascendant.name: rel.degree for rel in nu_fusion.ascendants_rels.all()} == {
        "Fusion": 1,
        "Rock": 2,
        "Jazz": 2,
    }

    exported_single = Genre.objects.build_criteria_tree(user, allows_multiple_primary_parents=False)
    exported_multi = Genre.objects.build_criteria_tree(user, allows_multiple_primary_parents=True)
    assert [node["secondary_parents"] for node in exported_single if node["name"] == "Rock"] == [["Q8341"]]
    assert [node["name"] for node in exported_multi] == ["Fusion"]
    assert exported_multi[0]["primary_parents"] == ["Q11399", "Q8341"]
    assert [child["name"] for child in exported_multi[0]["children"]] == ["Nu Fusion"]


@pytest.mark.django_db
def test_import_rejects_unknown_ref_and_primary_parents_in_single_tree(user, genre_type):
    unknown = [{"name": "Fusion", "id": "Q3", "children": [], "primary_parents": ["Q404"]}]
    assert error_code(lambda: import_tree(user, True, unknown)) == FieldValidationErrorCode.REFERENCE_INVALID
    assert error_code(lambda: import_tree(user, False, unknown)) == FieldValidationErrorCode.DEPENDENCY_MISSING
