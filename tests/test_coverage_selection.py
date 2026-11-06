import pytest
from django.contrib.auth import get_user_model
from django.db.models import IntegerField, Value
from rest_framework.exceptions import ValidationError

from tests.fixture_app.models import Criteria, CriteriaLineageRel, CriteriaPlaylist
from the_music_tree_genre_kit.criteria.selection.counts import CriteriaCoverageCounts
from the_music_tree_genre_kit.criteria.selection.coverage import (
    CriteriaCoverage,
    criteria_selection_predicate,
    parse_coverage,
)
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.serializer.model.criteria.playlist.output.summary import (
    CriteriaCoverageCountsSerializer,
    build_criteria_playlist_summary_serializer,
)
from the_music_tree_genre_kit.track.Track import Track


def make_criteria(user, kind, name, parent=None):
    criteria = Criteria(user=user, type=kind, _name=name, parent=parent)
    criteria.save()
    return criteria


def make_track(user, genre):
    track = Track(user=user, genre=genre)
    track.save()
    return track


@pytest.mark.parametrize("value", ["", "other", "genreOnly"])
def test_invalid_coverage(value):
    with pytest.raises(ValidationError):
        parse_coverage(value)


def test_coverage_defaults_and_requires_selection():
    assert parse_coverage(None, criteria_selected=False) == CriteriaCoverage.AND_DESCENDANTS
    assert parse_coverage("genre_only") == CriteriaCoverage.ONLY
    with pytest.raises(ValidationError):
        parse_coverage("genre_only", criteria_selected=False)


@pytest.mark.django_db
def test_selection_uses_primary_closure_and_preserves_population():
    user = get_user_model().objects.create(username="owner")
    other = get_user_model().objects.create(username="other")
    kind = CriteriaType.objects.create(label="genre")
    root = make_criteria(user, kind, "root")
    left = make_criteria(user, kind, "left", parent=root)
    right = make_criteria(user, kind, "right", parent=root)
    leaf = make_criteria(user, kind, "leaf", parent=left)
    secondary = make_criteria(user, kind, "secondary")
    # Model the materialized primary closure, including a diamond via left and right.
    for descendant, ascendant in [(left, root), (right, root), (leaf, root), (leaf, left), (leaf, right)]:
        CriteriaLineageRel.objects.create(user=user, descendant=descendant, ascendant=ascendant, degree=1)
    leaf.secondary_parents.add(secondary)
    own = make_track(user, root)
    child = make_track(user, leaf)
    genreless = make_track(user, None)
    make_track(other, leaf)
    scoped = Track.objects.filter(user=user)
    criteria = Criteria.objects.filter(user=user)

    def select(pk, coverage):
        return set(scoped.filter(criteria_selection_predicate(pk, coverage, criteria)).values_list("pk", flat=True))

    assert select(root.pk, CriteriaCoverage.ONLY) == {own.pk}
    assert select(root.pk, CriteriaCoverage.AND_DESCENDANTS) == {own.pk, child.pk}
    assert select(right.pk, CriteriaCoverage.AND_DESCENDANTS) == {child.pk}
    assert select(secondary.pk, CriteriaCoverage.AND_DESCENDANTS) == set()
    restricted = criteria.exclude(pk=root.pk)
    for coverage in CriteriaCoverage:
        predicate = criteria_selection_predicate(root.pk, coverage, restricted)
        assert not scoped.filter(predicate).exists()
    assert select(None, CriteriaCoverage.ONLY) == {genreless.pk}
    assert select(None, CriteriaCoverage.AND_DESCENDANTS) == {genreless.pk}


@pytest.mark.parametrize("exact,inclusive", [(-1, 0), (2, 1), (True, 1), (0, None)])
def test_invalid_count_projection(exact, inclusive):
    with pytest.raises(ValueError, match="Coverage counts must be"):
        CriteriaCoverageCounts(exact, inclusive)


def test_count_projection_serializer():
    counts = CriteriaCoverageCounts(0, 3)
    assert CriteriaCoverageCountsSerializer(counts).data == {
        "genre_only_tracks_count": 0,
        "genre_and_subgenres_tracks_count": 3,
    }


@pytest.mark.django_db
def test_summary_uses_prepared_counts_and_eager_loads(django_assert_num_queries):
    user = get_user_model().objects.create(username="owner")
    kind = CriteriaType.objects.create(label="genre")
    criteria = make_criteria(user, kind, "root")
    CriteriaPlaylist.objects.create(user=user, type=kind, criteria=criteria)
    serializer = build_criteria_playlist_summary_serializer(CriteriaPlaylist)
    queryset = CriteriaPlaylist.objects.annotate(
        genre_only_tracks_count=Value(0, output_field=IntegerField()),
        genre_and_subgenres_tracks_count=Value(2, output_field=IntegerField()),
    )
    with django_assert_num_queries(1):
        data = serializer(serializer.setup_queryset(queryset), many=True).data
    assert data[0]["name"] == "root"
    assert data[0]["genre_only_tracks_count"] == 0
    assert data[0]["genre_and_subgenres_tracks_count"] == 2
    with pytest.raises(AttributeError):
        serializer(CriteriaPlaylist.objects.first()).data
