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
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_import.serializer import CriteriaTreeImportSerializer
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_node import CriteriaTreeNodeSerializer


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
        tree_name="regional",
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
    fusion = make("Fusion", parent=rock, tree_name="regional", additional_primary_parents=[jazz])
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
    fusion = make("Fusion", parent=rock, tree_name="regional")

    assert (
        error_code(lambda: make("Plain", parent=rock, additional_primary_parents=[jazz]))
        == FieldValidationErrorCode.DEPENDENCY_MISSING
    )
    assert (
        error_code(lambda: make("Orphan", tree_name="regional", additional_primary_parents=[jazz]))
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
    fusion = make("Fusion", parent=rock, tree_name="regional", additional_primary_parents=[jazz])

    Criteria.objects.delete_instance(rock)

    fusion.refresh_from_db()
    assert fusion.parent == jazz and fusion.root == jazz
    assert list(fusion.additional_primary_parents.all()) == []
    assert ascendant_names(fusion) == {"Jazz"}


def import_tree(user, tree_name, tree):
    Genre.objects.import_criteria_tree(user, {"tree_name": tree_name, "tree": tree})


@pytest.mark.django_db
def test_import_scopes_by_tree_name_and_round_trips_parent_refs(user, genre_type):
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
    import_tree(user, "canonical", single_tree)
    import_tree(user, "regional", multi_tree)
    import_tree(user, "canonical", single_tree)

    fusion = Genre.objects.get(user=user, wikidata_id="Q1")
    nu_fusion = Genre.objects.get(user=user, wikidata_id="Q2")
    assert fusion.parent.name == "Rock" and nu_fusion.root_id == fusion.parent_id
    assert ascendant_names(nu_fusion) == {"Fusion", "Rock", "Jazz"}
    assert {rel.ascendant.name: rel.degree for rel in nu_fusion.ascendants_rels.all()} == {
        "Fusion": 1,
        "Rock": 2,
        "Jazz": 2,
    }

    exported_single = Genre.objects.build_criteria_tree(user, tree_name="canonical")
    exported_multi = Genre.objects.build_criteria_tree(user, tree_name="regional")
    assert [node["secondary_parents"] for node in exported_single if node["name"] == "Rock"] == [["Q8341"]]
    assert [node["name"] for node in exported_multi] == ["Fusion"]
    assert exported_multi[0]["primary_parents"] == ["Q11399", "Q8341"]
    assert [child["name"] for child in exported_multi[0]["children"]] == ["Nu Fusion"]


@pytest.mark.django_db
def test_import_rejects_unknown_ref_and_primary_parents_in_single_tree(user, genre_type):
    unknown = [{"name": "Fusion", "id": "Q3", "children": [], "primary_parents": ["Q404"]}]
    assert error_code(lambda: import_tree(user, "regional", unknown)) == FieldValidationErrorCode.REFERENCE_INVALID
    assert error_code(lambda: import_tree(user, "canonical", unknown)) == FieldValidationErrorCode.DEPENDENCY_MISSING


@pytest.mark.django_db
def test_import_flags_name_conflict_instead_of_failing(user, make, tag_type):
    make("Arabesque", criteria_type=tag_type)
    import_tree(user, "canonical", [{"name": "Pub rock", "id": "Q1431327", "children": []}])
    regional = [
        {"name": "pub rock", "id": "Q16250593", "children": [], "primary_parents": ["Q1431327"]},
        {"name": "arabesque", "id": "Q623824", "children": []},
    ]
    import_tree(user, "regional", regional)
    import_tree(user, "regional", regional)

    canonical = Genre.objects.get(user=user, wikidata_id="Q1431327")
    assert (canonical.name, canonical.has_name_conflict) == ("Pub rock", False)
    flagged = Genre.objects.filter(user=user, has_name_conflict=True).order_by("wikidata_id")
    assert [g.name for g in flagged] == ["pub rock (Q16250593)", "arabesque (Q623824)"]

    Genre.objects.filter(pk=flagged[0].pk).update(
        _name="pub rock (Australia)", is_manually_edited=True, has_name_conflict=False
    )
    import_tree(user, "regional", regional)
    assert Genre.objects.get(user=user, wikidata_id="Q16250593").name == "pub rock (Australia)"


@pytest.mark.django_db
def test_import_flags_umbrella_and_rewrites_it_even_on_locked_rows(user, genre_type):
    tree = [{"name": "Techno", "id": "Q170611", "is_umbrella": True, "children": [{"name": "Acid techno", "id": "Q1"}]}]
    import_tree(user, "canonical", tree)
    assert Genre.objects.get(user=user, wikidata_id="Q170611").is_umbrella
    assert not Genre.objects.get(user=user, wikidata_id="Q1").is_umbrella

    Genre.objects.filter(user=user, wikidata_id="Q170611").update(is_manually_edited=True)
    tree[0]["is_umbrella"] = False
    import_tree(user, "canonical", tree)
    assert not Genre.objects.get(user=user, wikidata_id="Q170611").is_umbrella


@pytest.mark.django_db
def test_import_sets_scene_and_rewrites_it_even_on_locked_rows(user, genre_type):
    tree = [
        {
            "name": "Core electronic",
            "id": "LOCAL:core-electronic",
            "children": [
                {"name": "Electronic dance music", "id": "Q851213", "scene": "commercial"},
                {"name": "Underground electronic", "id": "LOCAL:underground", "scene": "underground"},
            ],
        }
    ]
    import_tree(user, "canonical", tree)
    assert Genre.objects.get(user=user, wikidata_id="Q851213").scene == "commercial"
    assert Genre.objects.get(user=user, wikidata_id="LOCAL:core-electronic").scene is None

    Genre.objects.filter(user=user, wikidata_id="Q851213").update(is_manually_edited=True)
    tree[0]["children"][0]["scene"] = "underground"
    tree[0]["children"][1]["scene"] = "commercial"
    import_tree(user, "canonical", tree)
    assert Genre.objects.get(user=user, wikidata_id="Q851213").scene == "underground"

    del tree[0]["children"][0]["scene"]
    del tree[0]["children"][1]["scene"]
    import_tree(user, "canonical", tree)
    assert Genre.objects.get(user=user, wikidata_id="Q851213").scene is None


IMAGE = {
    "url": "https://upload.wikimedia.org/a.jpg",
    "page_url": "https://commons.wikimedia.org/wiki/File:A.jpg",
    "author": "Jane Doe",
    "license": "CC BY-SA 4.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
}


def _genre_image(user, key):
    genre = Genre.objects.get(user=user, wikidata_id=key)
    return genre.image_url, genre.image_author, genre.image_license


@pytest.mark.django_db
def test_import_sets_replaces_and_removes_the_image(user, genre_type):
    tree = [{"name": "Techno", "id": "Q170611", "image": IMAGE, "children": [{"name": "Acid", "id": "Q1"}]}]
    import_tree(user, "canonical", tree)
    assert _genre_image(user, "Q170611") == (IMAGE["url"], "Jane Doe", "CC BY-SA 4.0")
    assert _genre_image(user, "Q1") == (None, None, None)

    tree[0]["image"] = {**IMAGE, "url": "https://upload.wikimedia.org/b.jpg", "author": None}
    import_tree(user, "canonical", tree)
    assert _genre_image(user, "Q170611") == ("https://upload.wikimedia.org/b.jpg", None, "CC BY-SA 4.0")

    del tree[0]["image"]
    import_tree(user, "canonical", tree)
    assert _genre_image(user, "Q170611") == (None, None, None)


@pytest.mark.django_db
def test_import_rewrites_the_image_even_on_locked_rows(user, genre_type):
    tree = [
        {"name": "Techno", "id": "Q170611", "image": IMAGE, "children": [{"name": "Acid", "id": "Q1"}]},
    ]
    import_tree(user, "canonical", tree)
    Genre.objects.filter(user=user, wikidata_id__in=["Q170611", "Q1"]).update(is_manually_edited=True)

    tree[0]["image"] = {**IMAGE, "url": "https://upload.wikimedia.org/b.jpg"}
    tree[0]["children"][0]["image"] = IMAGE
    import_tree(user, "canonical", tree)
    assert _genre_image(user, "Q170611")[0] == "https://upload.wikimedia.org/b.jpg"
    assert _genre_image(user, "Q1")[0] == IMAGE["url"]

    del tree[0]["image"]
    import_tree(user, "canonical", tree)
    assert _genre_image(user, "Q170611") == (None, None, None)


@pytest.mark.parametrize(
    "image",
    [
        {**IMAGE, "url": "http://upload.wikimedia.org/a.jpg"},
        {**IMAGE, "license": ""},
        {**IMAGE, "extra": 1},
        "not-an-object",
    ],
)
def test_tree_node_serializer_rejects_an_invalid_image(image):
    serializer = CriteriaTreeNodeSerializer("tree", data={"name": "Techno", "id": "Q170611", "image": image})
    with pytest.raises(Exception, match=r"(?i)image"):
        serializer.is_valid(raise_exception=True)


def test_tree_node_serializer_accepts_a_valid_or_null_image():
    for image in (IMAGE, None):
        serializer = CriteriaTreeNodeSerializer("tree", data={"name": "Techno", "id": "Q170611", "image": image})
        assert serializer.is_valid(raise_exception=True)


@pytest.mark.django_db
def test_incomplete_image_hits_the_db_backstop_as_a_validation_error(user, genre_type):
    with pytest.raises(AppValidationException, match="image needs a url"):
        import_tree(user, "canonical", [{"name": "Techno", "id": "Q170611", "image": {"url": IMAGE["url"]}}])


def _split_tree(*children):
    return [{"name": "Core electronic", "id": "LOCAL:core-electronic", "children": list(children)}]


COMMERCIAL_NODE = {"name": "Electronic dance music", "id": "Q851213", "scene": "commercial"}
UNDERGROUND_NODE = {"name": "Underground electronic", "id": "LOCAL:underground", "scene": "underground"}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "children",
    [
        [COMMERCIAL_NODE, UNDERGROUND_NODE, {"name": "Techno", "id": "Q170611"}],
        [COMMERCIAL_NODE, {"name": "Techno", "id": "Q170611"}],
        [COMMERCIAL_NODE, {**UNDERGROUND_NODE, "scene": "commercial"}],
    ],
    ids=["stray-third-child", "missing-underground", "two-commercial"],
)
def test_import_rejects_scene_split_that_is_not_one_of_each(user, genre_type, children):
    with pytest.raises(AppValidationException) as raised:
        import_tree(user, "canonical", _split_tree(*children))

    assert "Core electronic" in str(raised.value.message)
    assert not Genre.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_import_accepts_scene_split_with_descendants_under_each_scene(user, genre_type):
    tree = _split_tree(
        {**COMMERCIAL_NODE, "children": [{"name": "House", "id": "Q20502"}, {"name": "Trance", "id": "Q170435"}]},
        {**UNDERGROUND_NODE, "children": [{"name": "Techno", "id": "Q170611"}]},
    )

    import_tree(user, "canonical", tree)

    assert Genre.objects.filter(user=user).count() == 6


@pytest.mark.django_db
def test_import_flags_unaccepted_root_until_parented_or_locked(user, genre_type):
    tree = [
        {"name": "Rock", "id": "Q11399", "children": []},
        {"name": "Pala", "id": "Q15724583", "children": [], "is_unaccepted_root": True},
    ]
    import_tree(user, "canonical", tree)
    flagged = Genre.objects.filter(user=user, is_unaccepted_root=True)
    assert [g.wikidata_id for g in flagged] == ["Q15724583"]

    parented = [{"name": "Rock", "id": "Q11399", "children": [{"name": "Pala", "id": "Q15724583", "children": []}]}]
    import_tree(user, "canonical", parented)
    assert not Genre.objects.filter(user=user, is_unaccepted_root=True).exists()

    import_tree(user, "canonical", tree)
    Genre.objects.filter(user=user, wikidata_id="Q15724583").update(is_unaccepted_root=False, is_manually_edited=True)
    import_tree(user, "canonical", tree)
    assert not Genre.objects.get(user=user, wikidata_id="Q15724583").is_unaccepted_root


@pytest.mark.django_db
def test_import_post_apply_check_ignores_same_qid_in_other_tree(user, genre_type):
    import_tree(user, "regional", [{"name": "Fusion", "id": "Q1", "children": []}])
    # Locked, so the canonical import can't adopt it and the QID ends up in both trees.
    Genre.objects.filter(user=user, wikidata_id="Q1").update(is_manually_edited=True)
    import_tree(
        user,
        "canonical",
        [{"name": "Rock", "id": "Q11399", "children": [{"name": "Fusion", "id": "Q1", "children": []}]}],
    )
    assert Genre.objects.filter(user=user, wikidata_id="Q1").count() == 2


@pytest.mark.django_db
def test_import_adopts_genre_moved_from_the_other_tree(user, genre_type):
    import_tree(user, "canonical", [{"name": "Metal", "id": "Q1", "children": []}])
    regional = [
        {
            "name": "Heavy metal",
            "id": "Q38848",
            "primary_parents": ["Q1"],
            "children": [{"name": "Regional metal", "id": "Q2", "children": []}],
        },
        {"name": "Folk", "id": "Q3", "children": []},
    ]
    import_tree(user, "regional", regional)
    moved = Genre.objects.get(user=user, wikidata_id="Q38848")
    locked = Genre.objects.get(user=user, wikidata_id="Q3")
    Genre.objects.filter(pk=locked.pk).update(is_manually_edited=True)

    canonical = [
        {
            "name": "Metal",
            "id": "Q1",
            "children": [
                {"name": "Heavy metal", "id": "Q38848", "children": []},
                {"name": "Folk", "id": "Q3", "children": []},
            ],
        }
    ]
    import_tree(user, "canonical", canonical)
    adopted = Genre.objects.get(user=user, wikidata_id="Q38848")
    assert (adopted.pk, adopted.tree_name, adopted.name, adopted.has_name_conflict) == (
        moved.pk,
        "canonical",
        "Heavy metal",
        False,
    )
    assert adopted.parent_id == Genre.objects.get(user=user, wikidata_id="Q1").pk
    assert set(Genre.objects.filter(user=user, wikidata_id="Q3").values_list("tree_name", "_name")) == {
        ("regional", "Folk"),
        ("canonical", "Folk (Q3)"),
    }

    import_tree(
        user, "regional", [{"name": "Regional metal", "id": "Q2", "primary_parents": ["Q38848"], "children": []}]
    )
    assert Genre.objects.get(user=user, wikidata_id="Q38848").pk == moved.pk
    regional_metal = Genre.objects.get(user=user, wikidata_id="Q2")
    assert (regional_metal.tree_name, regional_metal.parent.pk) == ("regional", moved.pk)


@pytest.mark.django_db
def test_import_leaves_genre_with_locked_descendant_in_the_other_tree(user, genre_type, tag_type):
    import_tree(user, "canonical", [{"name": "Metal", "id": "Q1", "children": []}])
    regional = [
        {
            "name": "Heavy metal",
            "id": "Q38848",
            "children": [
                {
                    "name": "Regional metal",
                    "id": "Q2",
                    "children": [{"name": "Local metal", "id": "Q4", "children": []}],
                }
            ],
        }
    ]
    import_tree(user, "regional", regional)
    old = Genre.objects.get(user=user, wikidata_id="Q38848")
    Genre.objects.filter(user=user, wikidata_id="Q4").update(is_manually_edited=True)

    import_tree(
        user,
        "canonical",
        [{"name": "Metal", "id": "Q1", "children": [{"name": "Heavy metal", "id": "Q38848", "children": []}]}],
    )
    assert set(Genre.objects.filter(user=user, wikidata_id="Q38848").values_list("tree_name", "_name")) == {
        ("regional", "Heavy metal"),
        ("canonical", "Heavy metal (Q38848)"),
    }

    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    import_tree(user, "regional", [{"name": "Regional metal", "id": "Q2", "children": []}])
    regional_metal = Genre.objects.get(user=user, wikidata_id="Q2")
    local_metal = Genre.objects.get(user=user, wikidata_id="Q4")
    assert not Genre.objects.filter(pk=old.pk).exists()
    assert (local_metal.parent_id, local_metal.root_id) == (regional_metal.pk, regional_metal.pk)


def import_with_cross_tree_links(user, tree_name, tree, links):
    Genre.objects.import_criteria_tree(
        user, {"tree_name": tree_name, "tree": tree, "cross_tree_secondary_parents": links}
    )


def secondary_parent_keys(wikidata_id, user):
    genre = Genre.objects.get(user=user, wikidata_id=wikidata_id, tree_name="canonical")
    return set(genre.secondary_parents.values_list("genre__wikidata_id", flat=True))


@pytest.mark.django_db
def test_regional_import_links_canonical_rows_to_regional_secondary_parents(user, genre_type):
    canonical = [
        {"name": "Reggae", "id": "Q9794", "children": [], "secondary_parents": ["Q8341"]},
        {"name": "Jazz", "id": "Q8341", "children": []},
    ]
    regional = [
        {"name": "Music of Jamaica", "id": "Q1", "children": []},
        {"name": "Caribbean", "id": "Q2", "children": []},
    ]
    import_tree(user, "canonical", canonical)
    import_with_cross_tree_links(user, "regional", regional, [{"id": "Q9794", "secondary_parents": ["Q1", "Q2"]}])
    assert secondary_parent_keys("Q9794", user) == {"Q8341", "Q1", "Q2"}

    import_with_cross_tree_links(user, "regional", regional, [{"id": "Q9794", "secondary_parents": ["Q2"]}])
    assert secondary_parent_keys("Q9794", user) == {"Q8341", "Q2"}

    import_tree(user, "regional", regional)
    assert secondary_parent_keys("Q9794", user) == {"Q8341", "Q2"}


@pytest.mark.django_db
def test_cross_tree_links_skip_locked_rows(user, genre_type):
    import_tree(user, "canonical", [{"name": "Reggae", "id": "Q9794", "children": []}])
    Genre.objects.filter(user=user, wikidata_id="Q9794").update(is_manually_edited=True)
    import_with_cross_tree_links(
        user,
        "regional",
        [{"name": "Music of Jamaica", "id": "Q1", "children": []}],
        [{"id": "Q9794", "secondary_parents": ["Q1"]}],
    )
    assert secondary_parent_keys("Q9794", user) == set()


@pytest.mark.django_db
def test_cross_tree_links_reject_unknown_or_same_tree_refs(user, genre_type):
    import_tree(user, "canonical", [{"name": "Reggae", "id": "Q9794", "children": []}])
    regional = [{"name": "Music of Jamaica", "id": "Q1", "children": []}]
    for links in (
        [{"id": "Q404", "secondary_parents": ["Q1"]}],
        [{"id": "Q9794", "secondary_parents": ["Q404"]}],
        [{"id": "Q1", "secondary_parents": ["Q1"]}],
        [{"id": "Q9794", "secondary_parents": ["Q9794"]}],
    ):
        assert (
            error_code(lambda links=links: import_with_cross_tree_links(user, "regional", regional, links))
            == FieldValidationErrorCode.REFERENCE_INVALID
        )


def test_tree_import_serializer_validates_cross_tree_links():
    tree = [{"name": "Music of Jamaica", "id": "Q1", "children": []}]
    links = [{"id": "Q9794", "secondary_parents": ["Q1"]}]
    valid = CriteriaTreeImportSerializer(
        data={"tree_name": "regional", "tree": tree, "cross_tree_secondary_parents": links}
    )
    assert valid.is_valid(), valid.errors
    assert [dict(link) for link in valid.validated_data["cross_tree_secondary_parents"]] == links
    for invalid_links in ({"Q9794": ["Q1"]}, [{"id": "Q9794", "secondary_parents": []}]):
        serializer = CriteriaTreeImportSerializer(
            data={"tree_name": "regional", "tree": tree, "cross_tree_secondary_parents": invalid_links}
        )
        assert not serializer.is_valid()


@pytest.mark.django_db
def test_cross_tree_links_reject_a_descendant_and_roll_back_on_dry_run(user, genre_type):
    import_tree(user, "canonical", [{"name": "Reggae", "id": "Q9794", "children": []}])
    regional = [{"name": "Jamaican reggae", "id": "Q1", "children": [], "primary_parents": ["Q9794"]}]
    assert (
        error_code(
            lambda: import_with_cross_tree_links(
                user, "regional", regional, [{"id": "Q9794", "secondary_parents": ["Q1"]}]
            )
        )
        == FieldValidationErrorCode.ANCESTOR_REFERENCE
    )

    Genre.objects.import_criteria_tree(
        user,
        {
            "tree_name": "regional",
            "tree": [{"name": "Music of Jamaica", "id": "Q2", "children": []}],
            "cross_tree_secondary_parents": [{"id": "Q9794", "secondary_parents": ["Q2"]}],
        },
        dry_run=True,
    )
    assert secondary_parent_keys("Q9794", user) == set()


@pytest.mark.django_db
def test_canonical_reimport_clears_cross_tree_links(user, genre_type):
    canonical = [{"name": "Reggae", "id": "Q9794", "children": []}]
    import_tree(user, "canonical", canonical)
    import_with_cross_tree_links(
        user,
        "regional",
        [{"name": "Music of Jamaica", "id": "Q1", "children": []}],
        [{"id": "Q9794", "secondary_parents": ["Q1"]}],
    )
    import_tree(user, "canonical", canonical)
    assert secondary_parent_keys("Q9794", user) == set()
