import pytest
from django.contrib.auth import get_user_model
from rest_framework import serializers

from tests.fixture_app.models import Criteria, CriteriaLineageRel, CriteriaPlaylist, Genre, Track, TrackPlaylistRel
from the_music_tree_genre_kit.criteria.CriteriaSide import CriteriaSide
from the_music_tree_genre_kit.criteria.playlist.bootstrap_criterialess_playlists_for_user import (
    bootstrap_criterialess_playlists_for_user,
)
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks
from the_music_tree_genre_kit.serializer.model.criteria.output.detailed_tracks import (
    build_criteria_detailed_tracks_fields,
)
from the_music_tree_genre_kit.serializer.model.criteria.output.minimum import build_criteria_minimum_serializer
from the_music_tree_genre_kit.serializer.model.criteria.output.simple import build_criteria_simple_serializer
from the_music_tree_genre_kit.serializer.model.criteria.playlist.output.minimum import (
    build_criteria_playlist_minimum_serializer,
)
from the_music_tree_genre_kit.serializer.model.criteria_lineage_rel.detailed import (
    build_criteria_lineage_rel_detailed_serializer,
)
from the_music_tree_genre_kit.serializer.model.criteria_lineage_rel.without_ascendant import (
    build_criteria_lineage_rel_without_ascendant_serializer,
)
from the_music_tree_genre_kit.serializer.model.criteria_lineage_rel.without_descendant import (
    build_criteria_lineage_rel_without_descendant_serializer,
)


@pytest.fixture
def criteria_tree(db):
    user = get_user_model().objects.create(username="fixture-user")
    criteria_type = CriteriaType.objects.create(label="genre")

    root = Criteria(user=user, type=criteria_type)
    root._name = "root"
    root.save()

    child = Criteria(user=user, type=criteria_type, parent=root)
    child._name = "child"
    child.save()

    lineage_rel = CriteriaLineageRel.objects.create(user=user, descendant=child, ascendant=root, degree=1)

    return root, child, lineage_rel


def test_criteria_minimum_serializer(criteria_tree):
    root, _child, _lineage_rel = criteria_tree

    serializer_class = build_criteria_minimum_serializer(Criteria)
    data = serializer_class(root).data

    assert data["uuid"] == str(root.uuid)
    assert data["name"] == "root"


def test_criteria_simple_serializer(criteria_tree):
    root, child, _lineage_rel = criteria_tree

    serializer_class = build_criteria_simple_serializer(Criteria)
    data = serializer_class(child).data

    assert data["uuid"] == str(child.uuid)
    assert data["name"] == "child"
    assert data["parent"]["uuid"] == str(root.uuid)
    assert data["parent"]["name"] == "root"


def test_criteria_simple_serializer_resolves_side_from_genre_mti_subtype(db):
    user = get_user_model().objects.create(username="fixture-user")
    genre_type = CriteriaType.objects.create(label="genre")

    root = Genre(user=user, type=genre_type)
    root._name = "root"
    root.save()
    genre = Genre(user=user, type=genre_type, parent=root, side=CriteriaSide.POP)
    genre._name = "child"
    genre.save()

    serializer_class = build_criteria_simple_serializer(Criteria)
    data = serializer_class(genre.criteria_ptr).data

    assert data["side"] == CriteriaSide.POP


def test_criteria_simple_serializer_side_is_none_for_non_genre_criteria(criteria_tree):
    root, _child, _lineage_rel = criteria_tree

    serializer_class = build_criteria_simple_serializer(Criteria)
    data = serializer_class(root).data

    assert data["side"] is None


def test_criteria_lineage_rel_detailed_serializer(criteria_tree):
    root, child, lineage_rel = criteria_tree

    serializer_class = build_criteria_lineage_rel_detailed_serializer(CriteriaLineageRel, Criteria)
    data = serializer_class(lineage_rel).data

    assert data["descendant"]["uuid"] == str(child.uuid)
    assert data["ascendant"]["uuid"] == str(root.uuid)
    assert data["degree"] == 1


def test_criteria_lineage_rel_without_ascendant_serializer(criteria_tree):
    _root, child, lineage_rel = criteria_tree

    serializer_class = build_criteria_lineage_rel_without_ascendant_serializer(CriteriaLineageRel, Criteria)
    data = serializer_class(lineage_rel).data

    assert data["descendant"]["uuid"] == str(child.uuid)
    assert data["degree"] == 1
    assert "ascendant" not in data


def test_criteria_lineage_rel_without_descendant_serializer(criteria_tree):
    root, _child, lineage_rel = criteria_tree

    serializer_class = build_criteria_lineage_rel_without_descendant_serializer(CriteriaLineageRel, Criteria)
    data = serializer_class(lineage_rel).data

    assert data["ascendant"]["uuid"] == str(root.uuid)
    assert data["degree"] == 1
    assert "descendant" not in data


def test_build_criteria_detailed_tracks_fields(db):
    user = get_user_model().objects.create(username="fixture-user")
    criteria_type = CriteriaType.objects.create(pk=int(CriteriaTypePks.GENRE), label="genre")
    CriteriaType.objects.create(pk=int(CriteriaTypePks.TAG), label="tag")
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    root_criteria = Criteria(user=user, type=criteria_type)
    root_criteria._name = "root"
    root_criteria.save()
    playlist = CriteriaPlaylist.objects.create(user=user, type=criteria_type, criteria=root_criteria)

    active_track = Track.objects.create(user=user, title="Active")
    archived_track = Track.objects.create(user=user, title="Archived", archived=True)
    TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=active_track)
    TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=archived_track)

    class TrackFixtureSerializer(serializers.ModelSerializer):
        class Meta:
            model = Track
            fields = ["uuid", "title"]

    tracks_fields = build_criteria_detailed_tracks_fields(
        TrackFixtureSerializer, "tracks", "tracks_count", "tracks_archived_count"
    )

    class PlaylistDetailedSerializer(serializers.ModelSerializer):
        tracks = tracks_fields["tracks"]
        tracks_count = tracks_fields["tracks_count"]
        tracks_archived_count = tracks_fields["tracks_archived_count"]

        class Meta:
            model = CriteriaPlaylist
            fields = ["uuid", "tracks", "tracks_count", "tracks_archived_count"]

    data = PlaylistDetailedSerializer(playlist).data

    assert data["tracks_count"] == 1
    assert data["tracks_archived_count"] == 1
    assert [track["title"] for track in data["tracks"]] == ["Active"]


def test_build_criteria_playlist_minimum_serializer(db):
    user = get_user_model().objects.create(username="fixture-user")
    criteria_type = CriteriaType.objects.create(label="genre")
    root = Criteria(user=user, type=criteria_type)
    root._name = "root-playlist-criteria"
    root.save()
    playlist = CriteriaPlaylist.objects.create(user=user, type=criteria_type, criteria=root)

    serializer_class = build_criteria_playlist_minimum_serializer(CriteriaPlaylist)
    data = serializer_class(playlist).data

    assert data["uuid"] == str(playlist.uuid)
    assert data["name"] == "root-playlist-criteria"
