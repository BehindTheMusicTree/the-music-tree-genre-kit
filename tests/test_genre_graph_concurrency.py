"""Real database locks: SQLite intentionally cannot stand in for these checks."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier, Event

import pytest
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor

from the_music_tree_genre_kit.genre_graph.models import GenreGraphAttribution, GenreGraphDataset, GenreGraphRevision
from the_music_tree_genre_kit.genre_graph.storage import (
    GraphRevisionConflict,
    graph_read_transaction,
    graph_write_transaction,
    replace_graph,
    replace_track_attributions,
    select_tracks,
)
from the_music_tree_genre_kit.track.Track import Track

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def postgres_only():
    if connection.vendor != "postgresql":
        pytest.skip("Requires explicit PostgreSQL test settings")


@pytest.fixture
def payload():
    return json.loads((Path(__file__).parent / "fixtures/genre_graph/regional-v2.json").read_text())


def in_connection(callback):
    try:
        return callback()
    finally:
        connections.close_all()


def test_e03_graph_migrations_reverse_and_reapply_without_losing_tracks(payload):
    track = Track(title="Survives graph migration rollback")
    Track.objects.bulk_create([track])
    previous = [("the_music_tree_genre_kit", "0015_trackplaylistrel_playlist_genre_pos_idx")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(previous)
        assert GenreGraphDataset._meta.db_table not in connection.introspection.table_names()
        assert Track.objects.get(pk=track.pk).title == track.title
    finally:
        MigrationExecutor(connection).migrate(latest)
    dataset = replace_graph(key="reference", payload=payload, expected_revision=None)
    replace_track_attributions(
        key=dataset.key,
        track_id=track.pk,
        attributions={"LOCAL:dub": {"decisionId": "rollback", "source": "fixture", "rationale": "test"}},
        expected_revision=dataset.revision,
    )
    assert select_tracks(Track.objects.all(), key=dataset.key, identity="LOCAL:dub").get().pk == track.pk


def test_e03_simultaneous_creation_has_one_winner_and_one_revision(payload, monkeypatch):
    barrier = Barrier(2, timeout=10)
    original = GenreGraphDataset.save

    def save(instance, *args, **kwargs):
        if instance._state.adding:
            barrier.wait()
        return original(instance, *args, **kwargs)

    monkeypatch.setattr(GenreGraphDataset, "save", save)

    def create():
        try:
            return replace_graph(key="reference", payload=payload, expected_revision=None).revision
        except GraphRevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(in_connection, create) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]
    assert results.count("conflict") == 1
    assert GenreGraphDataset.objects.count() == GenreGraphRevision.objects.count() == 1


def test_e03_reviewed_revision_cannot_be_overwritten_by_second_writer(payload):
    dataset = replace_graph(key="reference", payload=payload, expected_revision=None)
    barrier = Barrier(2, timeout=10)

    def update(name):
        changed = deepcopy(payload)
        changed["nodes"][0]["name"] = name
        barrier.wait()
        try:
            return replace_graph(key=dataset.key, payload=changed, expected_revision=dataset.revision).revision
        except GraphRevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(in_connection, lambda name=name: update(name)) for name in ("One", "Two")]
        results = [future.result(timeout=15) for future in futures]
    assert results.count("conflict") == 1
    assert GenreGraphRevision.objects.count() == 2


def test_e04_read_transaction_keeps_queries_and_tokens_consistent_during_import(payload):
    dataset = replace_graph(key="reference", payload=payload, expected_revision=None)
    track = Track(title="French")
    Track.objects.bulk_create([track])
    replace_track_attributions(
        key=dataset.key,
        track_id=track.pk,
        attributions={"LOCAL:french-dub": {"decisionId": "test", "source": "fixture", "rationale": "test"}},
        expected_revision=dataset.revision,
    )
    changed = deepcopy(payload)
    changed["relations"] = [
        edge
        for edge in changed["relations"]
        if not (edge["childId"] == "LOCAL:french-dub" and edge["type"] == "regional_membership")
    ]
    for node in changed["nodes"]:
        if node["id"] == "LOCAL:french-dub":
            node.pop("displayParentId", None)
    attempted = Event()

    def update():
        def mark_lock(execute, sql, params, many, context):
            if "FOR UPDATE" in sql:
                attempted.set()
            return execute(sql, params, many, context)

        with connection.execute_wrapper(mark_lock):
            return replace_graph(key=dataset.key, payload=changed, expected_revision=dataset.revision).revision

    def titles():
        return list(
            select_tracks(Track.objects.all(), key=dataset.key, identity="LOCAL:france").values_list("title", flat=True)
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with graph_read_transaction(key=dataset.key) as snapshot:
            assert titles() == ["French"]
            future = pool.submit(in_connection, update)
            assert attempted.wait(timeout=10)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
            assert titles() == ["French"]
            assert GenreGraphDataset.objects.get(pk=dataset.key).revision == snapshot.revision
        assert future.result(timeout=15) != dataset.revision
    assert titles() == []


@pytest.mark.parametrize("mutation", ["update", "delete", "track_delete"])
def test_e04_bulk_writer_locks_dataset_before_rows_used_by_service(payload, mutation):
    dataset = replace_graph(key="reference", payload=payload, expected_revision=None)
    track = Track(title="Reference")
    Track.objects.bulk_create([track])
    provenance = {"decisionId": "test", "source": "fixture", "rationale": "test"}
    replace_track_attributions(
        key=dataset.key,
        track_id=track.pk,
        attributions={"LOCAL:dub": provenance},
        expected_revision=dataset.revision,
    )
    attempted = Event()

    def bulk_write():
        def mark_attempt(execute, sql, params, many, context):
            if "FOR UPDATE" in sql or sql.startswith(("UPDATE", "DELETE")):
                attempted.set()
            return execute(sql, params, many, context)

        with (
            connection.execute_wrapper(mark_attempt),
            graph_write_transaction(key=dataset.key, expected_revision=dataset.revision),
        ):
            if mutation == "update":
                GenreGraphAttribution.objects.filter(track=track).update(
                    provenance={**provenance, "decisionId": "bulk"}
                )
            elif mutation == "delete":
                GenreGraphAttribution.objects.filter(track=track).delete()
            else:
                Track.objects.filter(pk=track.pk).delete()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with graph_write_transaction(key=dataset.key, expected_revision=dataset.revision):
            future = pool.submit(in_connection, bulk_write)
            assert attempted.wait(timeout=10)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
            replace_track_attributions(
                key=dataset.key,
                track_id=track.pk,
                attributions={"LOCAL:french-dub": provenance},
                expected_revision=dataset.revision,
            )
        future.result(timeout=15)
    if mutation == "update":
        attribution = GenreGraphAttribution.objects.get(track=track)
        assert attribution.node.identity == "LOCAL:french-dub"
        assert attribution.provenance["decisionId"] == "bulk"
    else:
        assert not GenreGraphAttribution.objects.filter(track=track).exists()
    assert Track.objects.filter(pk=track.pk).exists() == (mutation != "track_delete")


@pytest.mark.parametrize("first_operation", ["attribute", "transfer"])
def test_e02_attribution_and_owner_transfer_cannot_both_commit(payload, django_user_model, first_operation):
    dataset = replace_graph(key="reference", payload=payload, expected_revision=None)
    user = django_user_model.objects.create(username="personal")
    track = Track(title="Reference")
    Track.objects.bulk_create([track])
    node = dataset.nodes.get(identity="LOCAL:french-dub")
    attempted = Event()

    def mutate(operation):
        if operation == "attribute":
            GenreGraphAttribution.objects.bulk_create(
                [
                    GenreGraphAttribution(
                        track=track,
                        node=node,
                        provenance={"decisionId": "test", "source": "fixture", "rationale": "test"},
                    )
                ]
            )
        else:
            Track.objects.filter(pk=track.pk).update(user=user)

    def competing_write():
        def mark_attempt(execute, sql, params, many, context):
            if sql.startswith(("INSERT", "UPDATE")):
                attempted.set()
            return execute(sql, params, many, context)

        try:
            with transaction.atomic(), connection.execute_wrapper(mark_attempt):
                mutate("transfer" if first_operation == "attribute" else "attribute")
        except IntegrityError as error:
            assert "ownerless" in str(error)
            return "rejected"
        return "committed"

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            mutate(first_operation)
            future = pool.submit(in_connection, competing_write)
            assert attempted.wait(timeout=10)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
        assert future.result(timeout=15) == "rejected"
    track.refresh_from_db()
    assert (track.user_id is None) == (first_operation == "attribute")
    assert GenreGraphAttribution.objects.filter(track=track).exists() == (first_operation == "attribute")
