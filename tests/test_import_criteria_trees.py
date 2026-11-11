import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException

from tests.fixture_app.models import CriteriaPlaylist, Genre, Track, TrackPlaylistRel
from the_music_tree_genre_kit.criteria.playlist.bootstrap_criterialess_playlists_for_user import (
    bootstrap_criterialess_playlists_for_user,
)
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks


@pytest.fixture
def user():
    return get_user_model().objects.create(username="fixture-user")


@pytest.fixture(autouse=True)
def criteria_types_and_playlists(user):
    CriteriaType.objects.create(pk=int(CriteriaTypePks.GENRE), label="genre")
    CriteriaType.objects.create(pk=int(CriteriaTypePks.TAG), label="tag")
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)


def node(name, key, *children, **extra):
    return {"name": name, "id": key, "children": list(children), **extra}


def run(user, canonical, regional, **kwargs):
    return Genre.objects.import_criteria_trees(
        user,
        [{"tree_name": "canonical", "tree": canonical}, {"tree_name": "regional", "tree": regional}],
        **kwargs,
    )


def genre(user, key, tree_name=None):
    filters = {"tree_name": tree_name} if tree_name else {}
    return Genre.objects.get(user=user, wikidata_id=key, **filters)


def in_playlist(genre_row, track):
    return TrackPlaylistRel.objects.filter(playlist=genre_row.criteria_playlist, track=track).exists()


@pytest.mark.django_db
def test_reparent_inside_a_tree_moves_the_tracks_to_the_new_ascendants(user):
    run(user, [node("Electronic", "Q1", node("House", "Q2")), node("Dance", "Q3")], [])
    house = genre(user, "Q2")
    track = Track.objects.create(user=user, genre=house, title="Track")
    assert in_playlist(genre(user, "Q1"), track)

    run(user, [node("Electronic", "Q1"), node("Dance", "Q3", node("House", "Q2"))], [])

    assert genre(user, "Q2").pk == house.pk
    assert in_playlist(genre(user, "Q3"), track) and in_playlist(house, track)
    assert not in_playlist(genre(user, "Q1"), track)


@pytest.mark.django_db
def test_genre_moves_between_trees_in_either_direction_keeping_pk_and_tracks(user):
    run(
        user,
        [node("Metal", "Q1", node("Heavy metal", "Q2"))],
        [node("Folk", "Q3", node("Polka", "Q4"))],
    )
    heavy, polka = genre(user, "Q2"), genre(user, "Q4")
    heavy_track = Track.objects.create(user=user, genre=heavy, title="Heavy")
    polka_track = Track.objects.create(user=user, genre=polka, title="Polka")

    counts = run(
        user,
        [node("Metal", "Q1"), node("Folk", "Q3", node("Polka", "Q4"))],
        [node("Heavy metal", "Q2")],
    )

    assert counts["canonical"]["deleted_count"] == counts["regional"]["deleted_count"] == 0
    assert Genre.objects.filter(user=user, wikidata_id__in=["Q2", "Q4"]).count() == 2
    assert (genre(user, "Q2").pk, genre(user, "Q2").tree_name) == (heavy.pk, "regional")
    assert (genre(user, "Q4").pk, genre(user, "Q4").tree_name) == (polka.pk, "canonical")
    assert genre(user, "Q4").parent_id == genre(user, "Q3").pk
    assert genre(user, "Q2").parent_id is None
    assert TrackPlaylistRel.objects.filter(track=heavy_track, playlist=heavy.criteria_playlist).exists()
    assert not in_playlist(genre(user, "Q1"), heavy_track)
    assert in_playlist(genre(user, "Q3"), polka_track) and in_playlist(genre(user, "Q4"), polka_track)


@pytest.mark.django_db
def test_key_in_both_payloads_keeps_one_row_per_tree(user):
    run(user, [node("Fusion", "Q1")], [])
    canonical_row = genre(user, "Q1", "canonical")

    run(user, [node("Fusion", "Q1")], [node("Fusion", "Q1")])

    assert Genre.objects.filter(user=user, wikidata_id="Q1").count() == 2
    assert genre(user, "Q1", "canonical").pk == canonical_row.pk
    assert genre(user, "Q1", "regional").pk != canonical_row.pk


@pytest.mark.django_db
def test_genre_with_a_locked_descendant_is_replaced_not_moved(user):
    run(user, [node("Metal", "Q1")], [node("Heavy metal", "Q2", node("Local metal", "Q3"))])
    old = genre(user, "Q2")
    Genre.objects.filter(user=user, wikidata_id="Q3").update(is_manually_edited=True)

    run(user, [node("Metal", "Q1", node("Heavy metal", "Q2"))], [node("Local metal", "Q3")])

    moved = genre(user, "Q2", "canonical")
    assert moved.pk != old.pk
    assert not Genre.objects.filter(pk=old.pk).exists()


@pytest.mark.django_db
def test_names_are_disambiguated_across_trees_in_one_run(user):
    run(user, [node("Folk", "Q1")], [node("Folk", "Q2")])

    assert genre(user, "Q1").name == "Folk"
    assert genre(user, "Q2").name == "Folk (Q2)"
    assert genre(user, "Q2").has_name_conflict


@pytest.mark.django_db
def test_stale_guard_applies_per_tree_and_force_overrides_it(user):
    run(user, [node("A", "Q1"), node("B", "Q2"), node("C", "Q3")], [node("D", "Q4")])

    with pytest.raises(AppValidationException):
        run(user, [node("A", "Q1")], [node("D", "Q4")])
    assert Genre.objects.filter(user=user, tree_name="canonical").count() == 3

    run(user, [node("A", "Q1")], [node("D", "Q4")], force=True)
    assert Genre.objects.filter(user=user, tree_name="canonical").count() == 1


@pytest.mark.django_db
def test_dry_run_reports_counts_without_persisting(user):
    run(user, [node("A", "Q1")], [node("B", "Q2")])

    counts = run(user, [node("A", "Q1"), node("C", "Q3")], [node("B", "Q2"), node("D", "Q4")], dry_run=True)

    assert counts["canonical"]["created_count"] == counts["regional"]["created_count"] == 1
    assert counts["canonical"]["dry_run"] is True
    assert Genre.objects.filter(user=user).count() == 2


@pytest.mark.django_db
def test_same_tree_name_twice_is_rejected(user):
    with pytest.raises(AppValidationException):
        Genre.objects.import_criteria_trees(
            user, [{"tree_name": "canonical", "tree": []}, {"tree_name": "canonical", "tree": []}]
        )


def reparent_query_count(user, track_count):
    run(user, [node("Electronic", "Q1", node("House", "Q2")), node("Dance", "Q3")], [])
    house = genre(user, "Q2")
    for i in range(track_count):
        Track.objects.create(user=user, genre=house, title=f"Track {i}")
    with CaptureQueriesContext(connection) as queries:
        run(user, [node("Electronic", "Q1"), node("Dance", "Q3", node("House", "Q2"))], [])
    return len(queries)


@pytest.mark.django_db
def test_import_query_count_does_not_grow_with_the_tracks_of_a_moved_genre(user):
    small = reparent_query_count(user, 2)
    Genre.objects.filter(user=user).delete()
    Track.objects.all().delete()
    large = reparent_query_count(user, 30)
    assert large == small


@pytest.mark.django_db
def test_renamed_genre_frees_its_name_for_a_new_namesake_of_the_other_tree(user):
    run(user, [node("Folk", "Q1")], [])

    run(user, [node("Folk music", "Q1")], [node("Folk", "Q2")])

    assert genre(user, "Q1").name == "Folk music"
    assert (genre(user, "Q2").name, genre(user, "Q2").has_name_conflict) == ("Folk", False)


@pytest.mark.django_db
def test_primary_graph_of_the_ownerless_canonical_dataset_is_loadable(user):
    # The fixture models have a mandatory owner, so an ownerless import itself can't run here: this covers the
    # only owner-dependent lookup of the import (grow's canonical rows have `user IS NULL`).
    run(user, [node("Metal", "Q1")], [])
    assert Genre.objects._load_primary_graph(None) == ({}, {}, {})
    assert len(Genre.objects._load_primary_graph(user.pk)[0]) == 1
