import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APIClient

from tests.fixture_app.models import Criteria, CriteriaPlaylist, Track, TrackPlaylistRel
from the_music_tree_genre_kit.criteria.playlist.bootstrap_criterialess_playlists_for_user import (
    bootstrap_criterialess_playlists_for_user,
)
from the_music_tree_genre_kit.criteria.track_playlist_rel.tracks_count_annotation import tracks_count_annotation
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks

APP = "the_music_tree_genre_kit"


@pytest.fixture
def user():
    return get_user_model().objects.create(username="fixture-user")


@pytest.fixture
def playlist(user):
    genre_type = CriteriaType.objects.create(pk=int(CriteriaTypePks.GENRE), label="genre")
    CriteriaType.objects.create(pk=int(CriteriaTypePks.TAG), label="tag")
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)
    criteria = Criteria(user=user, type=genre_type)
    criteria._name = "House"
    criteria.save()
    return CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=criteria)


@pytest.mark.django_db
def test_duplicate_playlist_track_rel_is_rejected(user, playlist):
    track = Track.objects.create(user=user)
    TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=track)

    with pytest.raises(IntegrityError):
        TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=track)


@pytest.mark.django_db(transaction=True)
def test_migration_dedupes_and_renumbers_rels(user, playlist):
    first, second, unpositioned = (Track.objects.create(user=user) for _ in range(3))
    executor = MigrationExecutor(connection)
    executor.migrate([(APP, "0008_remove_track_archived")])
    old_rel = executor.loader.project_state([(APP, "0008_remove_track_archived")]).apps.get_model(
        APP, "TrackPlaylistRel"
    )
    for track_id, position in ((first.pk, 3), (first.pk, 7), (second.pk, 5), (unpositioned.pk, None)):
        old_rel.objects.create(user_id=user.pk, playlist_id=playlist.pk, track_id=track_id, position=position)

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())

    rels = TrackPlaylistRel.objects.filter(playlist=playlist).values_list("track_id", "position")
    assert sorted(rels, key=lambda rel: rel[1] or 0) == [(unpositioned.pk, None), (first.pk, 1), (second.pk, 2)]


@pytest.mark.django_db
def test_tracks_action_pages_rels_in_play_order(user, playlist):
    oldest, newest = Track.objects.create(user=user), Track.objects.create(user=user)
    TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=oldest)
    TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=newest)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(f"/criteria-playlists/{playlist.uuid}/tracks/", {"page_size": 1})

    assert response.status_code == 200
    assert response.data["overallTotal"] == 2
    assert response.data["results"] == [{"position": 1, "track": str(newest.uuid)}]


@pytest.fixture
def ordered_tracks(user, playlist):
    """Three tracks in play order; the last one is unpositioned (sorts after positioned rels)."""
    tracks = [Track.objects.create(user=user) for _ in range(3)]
    for track in tracks:
        TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=track)
    for track, position in zip(tracks, (1, 2, None), strict=True):
        TrackPlaylistRel.objects.filter(playlist=playlist, track=track).update(position=position)
    return tracks


def _get_tracks(user, playlist, **params):
    client = APIClient()
    client.force_authenticate(user=user)
    return client.get(f"/criteria-playlists/{playlist.uuid}/tracks/", params)


@pytest.mark.django_db
@pytest.mark.parametrize("start", [0, 1, 2])
def test_tracks_action_from_starts_at_track(user, playlist, ordered_tracks, start):
    response = _get_tracks(user, playlist, **{"from": str(ordered_tracks[start].uuid)})

    assert response.status_code == 200
    assert [rel["track"] for rel in response.data["results"]] == [str(t.uuid) for t in ordered_tracks[start:]]


@pytest.mark.django_db
def test_tracks_action_from_absent_track_is_404(user, playlist, ordered_tracks):
    outsider = Track.objects.create(user=user)

    assert _get_tracks(user, playlist, **{"from": str(outsider.uuid)}).status_code == 404


@pytest.mark.django_db
def test_tracks_action_from_malformed_uuid_is_400(user, playlist, ordered_tracks):
    assert _get_tracks(user, playlist, **{"from": "not-a-uuid"}).status_code == 400


@pytest.mark.django_db
def test_tracks_action_from_paginates(user, playlist, ordered_tracks):
    first_page = _get_tracks(user, playlist, page_size=1, **{"from": str(ordered_tracks[1].uuid)})
    second_page = _get_tracks(user, playlist, page_size=1, page=2, **{"from": str(ordered_tracks[1].uuid)})

    assert first_page.data["overallTotal"] == 2
    assert first_page.data["results"] == [{"position": 2, "track": str(ordered_tracks[1].uuid)}]
    assert second_page.data["results"] == [{"position": None, "track": str(ordered_tracks[2].uuid)}]


@pytest.mark.django_db
def test_tracks_count_annotation_counts_rels(user, playlist):
    TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=Track.objects.create(user=user))

    annotated = CriteriaPlaylist.objects.annotate(n=tracks_count_annotation()).get(pk=playlist.pk)

    assert annotated.n == 1
