import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException
from the_music_tree_api_kit.exception.validation.FieldValidationErrorCode import FieldValidationErrorCode

from tests.fixture_app.manager import CriteriaManager, GenreManager
from tests.fixture_app.models import Criteria, CriteriaPlaylist, Genre, Track, TrackPlaylistRel
from the_music_tree_genre_kit.criteria.children.genre.CriteriaSource import CriteriaSource
from the_music_tree_genre_kit.criteria.CriteriaSide import CriteriaSide
from the_music_tree_genre_kit.criteria.import_run.ImportRun import ImportRun
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
def test_save_with_duplicate_name_raises_app_validation_exception(user, genre_type):
    first = Criteria(user=user, type=genre_type)
    first._name = "Duplicate"
    first.save()

    second = Criteria(user=user, type=genre_type)
    second._name = "Duplicate"

    with pytest.raises(AppValidationException) as exc_info:
        second.save()
    assert exc_info.value.field_validation_error_code == FieldValidationErrorCode.NAME_DUPLICATE


@pytest.mark.django_db
def test_import_and_export_round_trip_preserves_pop_side(user, genre_type):
    tree_data = {
        "tree_name": "canonical",
        "tree": [
            {
                "name": "Electronic",
                "id": "Q9759",
                "children": [
                    {"name": "Core Electronic", "id": "LOCAL:core-electronic", "children": []},
                    {"name": "Pop Electronic", "id": "LOCAL:pop-electronic", "side": "pop", "children": []},
                ],
            }
        ],
    }

    Genre.objects.import_criteria_tree(user, tree_data)

    pop_child = Genre.objects.get(user=user, _name="Pop Electronic")
    assert pop_child.side == CriteriaSide.POP

    core_child = Genre.objects.get(user=user, _name="Core Electronic")
    assert core_child.side is None

    exported = Genre.objects.build_criteria_tree(user, tree_name="canonical")
    root_node = exported[0]
    exported_children_by_name = {child["name"]: child for child in root_node["children"]}

    assert exported_children_by_name["Pop Electronic"]["side"] == CriteriaSide.POP
    assert exported_children_by_name["Core Electronic"]["side"] is None


@pytest.mark.django_db
def test_import_root_with_only_core_child_keeps_side_null(user, genre_type):
    tree_data = {
        "tree_name": "canonical",
        "tree": [
            {"name": "Classical", "id": "Q9730", "children": [{"name": "Baroque", "id": "Q37853", "children": []}]}
        ],
    }

    Genre.objects.import_criteria_tree(user, tree_data)

    baroque = Genre.objects.get(user=user, _name="Baroque")
    assert baroque.side is None

    exported = Genre.objects.build_criteria_tree(user, tree_name="canonical")
    assert exported[0]["children"][0]["side"] is None


@pytest.mark.django_db
def test_import_criteria_tree_sets_ascendant_lineage_with_correct_degrees(user, genre_type):
    tree_data = {
        "tree_name": "canonical",
        "tree": [
            {
                "name": "Electronic",
                "id": "Q9759",
                "children": [
                    {
                        "name": "House",
                        "id": "Q186024",
                        "children": [{"name": "Deep House", "id": "Q1198500", "children": []}],
                    },
                ],
            }
        ],
    }

    Genre.objects.import_criteria_tree(user, tree_data)

    root = Genre.objects.get(user=user, _name="Electronic")
    child = Genre.objects.get(user=user, _name="House")
    grandchild = Genre.objects.get(user=user, _name="Deep House")

    assert {c.pk for c in child.ascendants.all()} == {root.pk}
    assert {c.pk for c in grandchild.ascendants.all()} == {root.pk, child.pk}

    grandchild_rels_by_ascendant = {rel.ascendant_id: rel.degree for rel in grandchild.ascendants_rels.all()}
    assert grandchild_rels_by_ascendant == {child.pk: 1, root.pk: 2}


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


def _save_genre(user, genre_type, name, parent=None, side=None):
    genre = Genre(user=user, type=genre_type, parent=parent, side=side)
    genre._name = name
    genre.save()
    return genre


@pytest.mark.django_db
def test_second_pop_side_sibling_raises(user, genre_type):
    root = _save_genre(user, genre_type, "root")
    _save_genre(user, genre_type, "first-pop", parent=root, side=CriteriaSide.POP)

    with pytest.raises(AppValidationException) as exc_info:
        _save_genre(user, genre_type, "second-pop", parent=root, side=CriteriaSide.POP)

    assert exc_info.value.field_validation_error_code == FieldValidationErrorCode.REFERENCE_INVALID
    assert Genre.objects.filter(root=root, side=CriteriaSide.POP).count() == 1


@pytest.mark.django_db
def test_resaving_existing_pop_child_allowed(user, genre_type):
    root = _save_genre(user, genre_type, "root")
    pop_child = _save_genre(user, genre_type, "pop", parent=root, side=CriteriaSide.POP)

    Genre.objects.update_instance(pop_child, name="pop-renamed")

    assert Genre.objects.get(pk=pop_child.pk).side == CriteriaSide.POP


@pytest.mark.django_db
def test_new_pop_child_allowed_after_previous_moved_to_core(user, genre_type):
    root = _save_genre(user, genre_type, "root")
    old_pop_child = _save_genre(user, genre_type, "old-pop", parent=root, side=CriteriaSide.POP)
    Genre.objects.update_instance(old_pop_child, side=CriteriaSide.CORE)

    new_pop_child = _save_genre(user, genre_type, "new-pop", parent=root, side=CriteriaSide.POP)

    assert list(Genre.objects.filter(root=root, side=CriteriaSide.POP)) == [new_pop_child]


def _electronic_tree(first_side, second_side):
    return {
        "tree_name": "canonical",
        "tree": [
            {
                "name": "Electronic",
                "id": "Q9759",
                "children": [
                    {"name": "First", "id": "LOCAL:first", "side": first_side, "children": []},
                    {"name": "Second", "id": "LOCAL:second", "side": second_side, "children": []},
                ],
            }
        ],
    }


@pytest.mark.django_db
def test_import_with_two_pop_siblings_raises(user, genre_type):
    with pytest.raises(AppValidationException) as exc_info:
        Genre.objects.import_criteria_tree(user, _electronic_tree("pop", "pop"))

    assert exc_info.value.field_validation_error_code == FieldValidationErrorCode.REFERENCE_INVALID
    assert not Genre.objects.filter(user=user, side=CriteriaSide.POP).exists()


@pytest.mark.django_db
def test_import_moves_pop_side_between_existing_siblings(user, genre_type):
    Genre.objects.import_criteria_tree(user, _electronic_tree("pop", None))

    Genre.objects.import_criteria_tree(user, _electronic_tree(None, "pop"))

    assert list(Genre.objects.filter(user=user, side=CriteriaSide.POP).values_list("_name", flat=True)) == ["Second"]


@pytest.mark.django_db
def test_import_criteria_tree_calls_on_bulk_created_once_with_full_tree(user, genre_type, monkeypatch):
    tree_data = {
        "tree_name": "canonical",
        "tree": [
            {"name": "Electronic", "id": "Q9759", "children": [{"name": "House", "id": "Q186024", "children": []}]},
        ],
    }

    captured: list = []
    monkeypatch.setattr(
        GenreManager, "_on_bulk_created", lambda self, instances, actor=None: captured.append(instances)
    )

    Genre.objects.import_criteria_tree(user, tree_data)

    assert len(captured) == 1
    assert {instance._name for instance in captured[0]} == {"Electronic", "House"}


@pytest.mark.django_db
def test_bulk_create_for_criteria_creates_playlists_matching_criteria_tree(user, genre_type, monkeypatch):
    tree_data = {
        "tree_name": "canonical",
        "tree": [
            {
                "name": "Electronic",
                "id": "Q9759",
                "children": [
                    {
                        "name": "House",
                        "id": "Q186024",
                        "children": [{"name": "Deep House", "id": "Q1198500", "children": []}],
                    }
                ],
            }
        ],
    }

    monkeypatch.setattr(
        GenreManager,
        "_on_bulk_created",
        lambda self, instances, actor=None: CriteriaPlaylist.objects.bulk_create_for_criteria(instances),
    )

    Genre.objects.import_criteria_tree(user, tree_data)

    root = Genre.objects.get(user=user, _name="Electronic")
    child = Genre.objects.get(user=user, _name="House")
    grandchild = Genre.objects.get(user=user, _name="Deep House")

    root_playlist = CriteriaPlaylist.objects.get(criteria=root)
    child_playlist = CriteriaPlaylist.objects.get(criteria=child)
    grandchild_playlist = CriteriaPlaylist.objects.get(criteria=grandchild)

    assert root_playlist.parent is None
    assert root_playlist.root == root_playlist

    assert child_playlist.parent == root_playlist
    assert child_playlist.root == root_playlist

    assert grandchild_playlist.parent == child_playlist
    assert grandchild_playlist.root == root_playlist


@pytest.mark.django_db
def test_bulk_create_for_criteria_resolves_root_that_predates_the_batch(user, genre_type, monkeypatch):
    monkeypatch.setattr(
        GenreManager,
        "_on_bulk_created",
        lambda self, instances, actor=None: CriteriaPlaylist.objects.bulk_create_for_criteria(instances),
    )

    Genre.objects.import_criteria_tree(
        user,
        {"tree_name": "canonical", "tree": [{"name": "Electronic", "id": "Q9759", "children": []}]},
    )

    # Partial reimport: "Electronic" already exists and is matched in place, so only "House"
    # is new -- its root ("Electronic") is absent from this batch and must be looked up in the DB.
    Genre.objects.import_criteria_tree(
        user,
        {
            "tree_name": "canonical",
            "tree": [
                {"name": "Electronic", "id": "Q9759", "children": [{"name": "House", "id": "Q186024", "children": []}]}
            ],
        },
    )

    root = Genre.objects.get(user=user, _name="Electronic")
    child = Genre.objects.get(user=user, _name="House")

    root_playlist = CriteriaPlaylist.objects.get(criteria=root)
    child_playlist = CriteriaPlaylist.objects.get(criteria=child)

    assert child_playlist.parent == root_playlist
    assert child_playlist.root == root_playlist


@pytest.mark.django_db
def test_import_criteria_tree_moving_a_criteria_moves_its_playlist(user, genre_type, monkeypatch):
    monkeypatch.setattr(
        GenreManager,
        "_on_bulk_created",
        lambda self, instances, actor=None: CriteriaPlaylist.objects.bulk_create_for_criteria(instances),
    )
    house = {"name": "House", "id": "Q186024", "children": []}
    Genre.objects.import_criteria_tree(
        user,
        {
            "tree_name": "canonical",
            "tree": [
                {"name": "Electronic", "id": "Q9759", "children": [house]},
                {"name": "Dance", "id": "Q1", "children": []},
            ],
        },
    )

    Genre.objects.import_criteria_tree(
        user,
        {
            "tree_name": "canonical",
            "tree": [
                {"name": "Electronic", "id": "Q9759", "children": []},
                {"name": "Dance", "id": "Q1", "children": [house]},
            ],
        },
    )

    dance_playlist = CriteriaPlaylist.objects.get(criteria__in=Genre.objects.filter(user=user, _name="Dance"))
    house_playlist = CriteriaPlaylist.objects.get(criteria__in=Genre.objects.filter(user=user, _name="House"))
    assert house_playlist.parent == dance_playlist
    assert house_playlist.root == dance_playlist
    assert list(dance_playlist.children) == [house_playlist]


@pytest.mark.django_db
def test_import_criteria_tree_with_empty_name_raises_app_validation_exception(user, genre_type):
    tree_data = {"tree_name": "canonical", "tree": [{"name": "", "children": []}]}

    with pytest.raises(AppValidationException):
        Genre.objects.import_criteria_tree(user, tree_data)


@pytest.mark.django_db
def test_import_criteria_tree_sets_wikidata_id(user, genre_type):
    tree_data = {
        "tree_name": "canonical",
        "tree": [{"name": "Electronic", "id": "Q9759", "children": []}],
    }

    Genre.objects.import_criteria_tree(user, tree_data)

    electronic = Genre.objects.get(user=user, _name="Electronic")
    assert electronic.wikidata_id == "Q9759"


@pytest.mark.django_db
def test_reimport_with_same_wikidata_id_updates_existing_row_in_place(user, genre_type):
    Genre.objects.import_criteria_tree(
        user,
        {"tree_name": "canonical", "tree": [{"name": "Electronic", "id": "Q9759", "children": []}]},
    )
    original = Genre.objects.get(user=user, wikidata_id="Q9759")

    Genre.objects.import_criteria_tree(
        user,
        {
            "tree_name": "canonical",
            "tree": [{"name": "Electronic Music", "id": "Q9759", "children": []}],
        },
    )

    updated = Genre.objects.get(user=user, wikidata_id="Q9759")
    assert updated.pk == original.pk
    assert updated._name == "Electronic Music"
    assert Genre.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_genre_node_without_wikidata_id_is_rejected(user, genre_type):
    with pytest.raises(AppValidationException) as exc_info:
        Genre.objects.import_criteria_tree(
            user, {"tree_name": "canonical", "tree": [{"name": "Manual Genre", "children": []}]}
        )

    assert exc_info.value.field_validation_error_code == FieldValidationErrorCode.REQUIRED
    assert not Genre.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_genre_child_node_without_wikidata_id_is_rejected(user, genre_type):
    tree_data = {
        "tree_name": "canonical",
        "tree": [{"name": "Electronic", "id": "Q9759", "children": [{"name": "House", "children": []}]}],
    }

    with pytest.raises(AppValidationException) as exc_info:
        Genre.objects.import_criteria_tree(user, tree_data)

    assert exc_info.value.field_validation_error_code == FieldValidationErrorCode.REQUIRED
    assert not Genre.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_genre_absent_from_reimport_matched_by_wikidata_id_is_deleted(user, genre_type, tag_type, monkeypatch):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    monkeypatch.setattr(
        GenreManager,
        "_on_bulk_created",
        lambda self, instances, actor=None: CriteriaPlaylist.objects.bulk_create_for_criteria(instances),
    )

    Genre.objects.import_criteria_tree(
        user,
        {"tree_name": "canonical", "tree": [{"name": "Electronic", "id": "Q9759", "children": []}]},
    )
    assert Genre.objects.filter(user=user, wikidata_id="Q9759").exists()

    # Deleting the only existing pipeline row is a 100% stale-delete, so the size guard
    # requires force=True here (see test_reimport_refuses_large_stale_delete_without_force).
    Genre.objects.import_criteria_tree(
        user,
        {"tree_name": "canonical", "tree": [{"name": "Classical", "id": "Q9730", "children": []}]},
        force=True,
    )

    assert not Genre.objects.filter(user=user, wikidata_id="Q9759").exists()
    assert Genre.objects.filter(user=user, wikidata_id="Q9730").exists()


@pytest.mark.django_db
def test_reimport_reparents_track_off_a_deleted_stale_genre_instead_of_raising(user, genre_type, tag_type, monkeypatch):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    monkeypatch.setattr(
        GenreManager,
        "_on_bulk_created",
        lambda self, instances, actor=None: CriteriaPlaylist.objects.bulk_create_for_criteria(instances),
    )

    Genre.objects.import_criteria_tree(
        user,
        {
            "tree_name": "canonical",
            "tree": [
                {
                    "name": "Electronic",
                    "id": "Q9759",
                    "children": [{"name": "House", "id": "Q186024", "children": []}],
                }
            ],
        },
    )
    house = Genre.objects.get(user=user, wikidata_id="Q186024")
    track = Track.objects.create(user=user, genre=house)

    # "House" (Q186024) is dropped from this reimport -- a raw bulk `.delete()` of the stale
    # row would raise (Track.genre is on_delete=DO_NOTHING); the fix reparents the track instead.
    Genre.objects.import_criteria_tree(
        user,
        {"tree_name": "canonical", "tree": [{"name": "Electronic", "id": "Q9759", "children": []}]},
    )

    assert not Genre.objects.filter(user=user, wikidata_id="Q186024").exists()
    track.refresh_from_db()
    assert track.genre_id == Genre.objects.get(user=user, wikidata_id="Q9759").pk


@pytest.mark.django_db
def test_manually_edited_genre_keeps_its_name_and_parent_across_reimport(user, genre_type, tag_type, monkeypatch):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    monkeypatch.setattr(
        GenreManager,
        "_on_bulk_created",
        lambda self, instances, actor=None: CriteriaPlaylist.objects.bulk_create_for_criteria(instances),
    )

    Genre.objects.import_criteria_tree(
        user,
        {
            "tree_name": "canonical",
            "tree": [
                {
                    "name": "Electronic",
                    "id": "Q9759",
                    "children": [{"name": "House", "id": "Q186024", "children": []}],
                }
            ],
        },
    )
    house = Genre.objects.get(user=user, wikidata_id="Q186024")
    house.is_manually_edited = True
    house._name = "House (curated)"
    house.parent = None
    house.root = house
    house.save(update_fields=["is_manually_edited", "_name", "parent", "root"])

    Genre.objects.import_criteria_tree(
        user,
        {
            "tree_name": "canonical",
            "tree": [
                {
                    "name": "Electronic",
                    "id": "Q9759",
                    "children": [{"name": "House", "id": "Q186024", "children": []}],
                }
            ],
        },
    )

    house.refresh_from_db()
    assert house._name == "House (curated)"
    assert house.parent is None


@pytest.mark.django_db
def test_excluded_genre_is_neither_recreated_nor_deleted_by_reimport(user, genre_type, tag_type, monkeypatch):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    monkeypatch.setattr(
        GenreManager,
        "_on_bulk_created",
        lambda self, instances, actor=None: CriteriaPlaylist.objects.bulk_create_for_criteria(instances),
    )

    Genre.objects.import_criteria_tree(
        user,
        {"tree_name": "canonical", "tree": [{"name": "Electronic", "id": "Q9759", "children": []}]},
    )
    electronic = Genre.objects.get(user=user, wikidata_id="Q9759")
    electronic.is_excluded = True
    electronic.save(update_fields=["is_excluded"])

    # Reimport with the wikidata_id absent -- a normal row would be deleted here.
    Genre.objects.import_criteria_tree(
        user, {"tree_name": "canonical", "tree": [{"name": "Classical", "id": "Q9730", "children": []}]}
    )
    assert Genre.objects.filter(user=user, wikidata_id="Q9759").exists()

    # Reimport with the wikidata_id present again -- an excluded row must not be touched.
    Genre.objects.import_criteria_tree(
        user,
        {
            "tree_name": "canonical",
            "tree": [{"name": "Electronic Renamed", "id": "Q9759", "children": []}],
        },
    )
    electronic.refresh_from_db()
    assert electronic._name == "Electronic"
    assert Genre.objects.filter(user=user, wikidata_id="Q9759").count() == 1


@pytest.mark.django_db
def test_reimport_with_empty_tree_deletes_previously_wikidata_tagged_genres(user, genre_type, tag_type, monkeypatch):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    monkeypatch.setattr(
        GenreManager,
        "_on_bulk_created",
        lambda self, instances, actor=None: CriteriaPlaylist.objects.bulk_create_for_criteria(instances),
    )

    Genre.objects.import_criteria_tree(
        user,
        {"tree_name": "canonical", "tree": [{"name": "Electronic", "id": "Q9759", "children": []}]},
    )
    assert Genre.objects.filter(user=user, wikidata_id="Q9759").exists()

    Genre.objects.import_criteria_tree(user, {"tree_name": "canonical", "tree": []}, force=True)

    assert not Genre.objects.filter(user=user, wikidata_id="Q9759").exists()


@pytest.mark.django_db
def test_tag_import_criteria_tree_delete_and_recreate_unaffected(user, genre_type, tag_type, monkeypatch):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    monkeypatch.setattr(
        CriteriaManager,
        "_on_bulk_created",
        lambda self, instances, actor=None: CriteriaPlaylist.objects.bulk_create_for_criteria(instances),
    )

    Criteria.objects.import_criteria_tree(user, {"tree_name": "canonical", "tree": [{"name": "Chill", "children": []}]})
    original = Criteria.objects.get(user=user, _name="Chill")

    Criteria.objects.import_criteria_tree(user, {"tree_name": "canonical", "tree": [{"name": "Chill", "children": []}]})

    recreated = Criteria.objects.get(user=user, _name="Chill")
    assert recreated.pk != original.pk


@pytest.mark.django_db
def test_import_disambiguates_case_insensitive_duplicate_names(user, genre_type):
    tree_data = {
        "tree_name": "canonical",
        "tree": [
            {"name": "House", "id": "Q186024", "children": []},
            {"name": "house", "id": "Q999999", "children": []},
        ],
    }

    Genre.objects.import_criteria_tree(user, tree_data)

    assert set(Genre.objects.filter(user=user).values_list("_name", "has_name_conflict")) == {
        ("House", False),
        ("house (Q999999)", True),
    }


@pytest.mark.django_db
def test_dry_run_import_writes_nothing(user, genre_type):
    result = Genre.objects.import_criteria_tree(
        user,
        {"tree_name": "canonical", "tree": [{"name": "Electronic", "id": "Q9759", "children": []}]},
        dry_run=True,
    )

    assert result == {"created_count": 1, "updated_count": 0, "deleted_count": 0, "dry_run": True}
    assert not Genre.objects.filter(user=user).exists()
    assert not ImportRun.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_reimport_refuses_large_stale_delete_without_force(user, genre_type, tag_type, monkeypatch):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    monkeypatch.setattr(
        GenreManager,
        "_on_bulk_created",
        lambda self, instances, actor=None: CriteriaPlaylist.objects.bulk_create_for_criteria(instances),
    )

    Genre.objects.import_criteria_tree(
        user,
        {
            "tree_name": "canonical",
            "tree": [
                {"name": "Electronic", "id": "Q9759", "children": []},
                {"name": "Classical", "id": "Q9730", "children": []},
                {"name": "Jazz", "id": "Q8341", "children": []},
            ],
        },
    )

    with pytest.raises(AppValidationException) as exc_info:
        Genre.objects.import_criteria_tree(
            user,
            {"tree_name": "canonical", "tree": [{"name": "Electronic", "id": "Q9759", "children": []}]},
        )
    assert exc_info.value.field_validation_error_code == FieldValidationErrorCode.DEFAULT
    assert Genre.objects.filter(user=user).count() == 3

    Genre.objects.import_criteria_tree(
        user,
        {"tree_name": "canonical", "tree": [{"name": "Electronic", "id": "Q9759", "children": []}]},
        force=True,
    )
    assert Genre.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_reimport_spares_app_and_admin_sourced_genres(user, genre_type):
    app_genre = Genre.objects.create(user=user, _name="App Genre", source=CriteriaSource.APP)
    admin_genre = Genre.objects.create(
        user=user, _name="Admin Genre", source=CriteriaSource.ADMIN, wikidata_id="LOCAL:admin-genre"
    )

    Genre.objects.import_criteria_tree(
        user,
        {"tree_name": "canonical", "tree": [{"name": "Electronic", "id": "Q9759", "children": []}]},
    )

    assert Genre.objects.filter(pk=app_genre.pk).exists()
    assert Genre.objects.filter(pk=admin_genre.pk).exists()
    assert Genre.objects.filter(user=user, wikidata_id="Q9759").exists()


@pytest.mark.django_db
def test_import_adopts_legacy_unkeyed_pipeline_row_by_name(user, genre_type):
    legacy = Genre.objects.create(user=user, _name="electronic", source=CriteriaSource.PIPELINE)

    Genre.objects.import_criteria_tree(
        user,
        {"tree_name": "canonical", "tree": [{"name": "Electronic", "id": "Q9759", "children": []}]},
    )

    adopted = Genre.objects.get(user=user)
    assert adopted.pk == legacy.pk
    assert adopted.wikidata_id == "Q9759" and adopted._name == "Electronic"


def _import_house(user, **house_extra):
    Genre.objects.import_criteria_tree(
        user,
        {
            "tree_name": "canonical",
            "tree": [
                {
                    "name": "Electronic",
                    "id": "Q9759",
                    "children": [{"name": "House", "id": "Q186024", "children": [], **house_extra}],
                }
            ],
        },
    )
    return Genre.objects.get(user=user, wikidata_id="Q186024")


@pytest.fixture
def stub_playlists(user, monkeypatch):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    monkeypatch.setattr(
        GenreManager,
        "_on_bulk_created",
        lambda self, instances, actor=None: CriteriaPlaylist.objects.bulk_create_for_criteria(instances),
    )


@pytest.mark.django_db
def test_import_saves_summary_description_and_source_url_then_nulls_them(user, genre_type, tag_type, stub_playlists):
    texts = {
        "summary": "House is a genre.",
        "description": "music genre",
        "summary_source_url": "https://en.wikipedia.org/wiki/House_music",
    }
    house = _import_house(user, **texts)
    assert (house.summary, house.description, house.summary_source_url) == tuple(texts.values())

    house = _import_house(user, **{**texts, "summary": "Updated."})
    assert house.summary == "Updated."

    house = _import_house(user)
    assert (house.summary, house.description, house.summary_source_url) == (None, None, None)


@pytest.mark.django_db
def test_locked_genre_keeps_admin_summary_across_reimport(user, genre_type, tag_type, stub_playlists):
    house = _import_house(user)
    Genre.objects.filter(pk=house.pk).update(is_manually_edited=True)
    Genre.objects.filter(pk=house.pk).update(summary="Admin text.")

    house = _import_house(
        user, summary="Wiki text.", description="music genre", summary_source_url="https://en.wikipedia.org/wiki/X"
    )

    assert (house.summary, house.description, house.summary_source_url) == ("Admin text.", None, None)


@pytest.mark.django_db
def test_reparent_query_count_is_independent_of_track_count(user, genre_type, tag_type):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)

    def count_reparent_queries(track_count):
        def genre(name, parent=None):
            criteria = Criteria(user=user, type=genre_type, parent=parent)
            criteria._name = name
            criteria.save()
            CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=criteria)
            return criteria

        root = genre(f"root{track_count}")
        old_parent = genre(f"old{track_count}", root)
        new_parent = genre(f"new{track_count}", root)
        moved = genre(f"moved{track_count}", old_parent)
        for _ in range(track_count):
            Track.objects.create(user=user, genre=moved)
        with CaptureQueriesContext(connection) as queries:
            Criteria.objects.update_instance(moved, parent=new_parent)
        return len(queries.captured_queries)

    assert count_reparent_queries(2) == count_reparent_queries(8)
