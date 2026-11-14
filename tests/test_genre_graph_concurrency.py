"""Real database locks: SQLite intentionally cannot stand in for these checks."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier, Event

import pytest
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor

from the_music_tree_genre_kit.genre_graph.models import (
    GenreGraphAssignmentState,
    GenreGraphAttribution,
    GenreGraphAttributionEvidence,
    GenreGraphAttributionRevision,
    GenreGraphDataset,
    GenreGraphEvidence,
    GenreGraphRevision,
)
from the_music_tree_genre_kit.genre_graph.storage import (
    GraphRevisionConflict,
    graph_read_snapshot,
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
        attributions={"LOCAL:dub": [{"decisionId": "rollback", "source": "fixture", "rationale": "test"}]},
        expected_revision=dataset.revision,
        expected_assignment_revision=None,
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
        attributions={"LOCAL:french-dub": [{"decisionId": "test", "source": "fixture", "rationale": "test"}]},
        expected_revision=dataset.revision,
        expected_assignment_revision=None,
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
            assert future.result(timeout=15) != dataset.revision
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
        attributions={"LOCAL:dub": [provenance]},
        expected_revision=dataset.revision,
        expected_assignment_revision=None,
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
                GenreGraphAttribution.objects.get(track=track).evidence.add(
                    GenreGraphEvidence.objects.create(
                        dataset=dataset, decision_id="bulk", source="fixture", rationale="test"
                    )
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
                attributions={"LOCAL:french-dub": [provenance]},
                expected_revision=dataset.revision,
                expected_assignment_revision=GenreGraphAssignmentState.objects.get(
                    dataset=dataset, track=track
                ).revision,
            )
        future.result(timeout=15)
    if mutation == "update":
        attribution = GenreGraphAttribution.objects.get(track=track)
        assert attribution.node.identity == "LOCAL:french-dub"
        assert set(attribution.evidence.values_list("decision_id", flat=True)) == {"test", "bulk"}
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


def test_populated_assignment_migration_preserves_historical_evidence(payload):
    song = Track(title="Migrated")
    Track.objects.bulk_create([song])
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    previous = [("the_music_tree_genre_kit", "0019_dataset_owned_access")]
    executor.migrate(previous)
    old = executor.loader.project_state(previous).apps
    dataset_model = old.get_model("the_music_tree_genre_kit", "GenreGraphDataset")
    node_model = old.get_model("the_music_tree_genre_kit", "GenreGraphNode")
    assignment_model = old.get_model("the_music_tree_genre_kit", "GenreGraphAttribution")
    history_model = old.get_model("the_music_tree_genre_kit", "GenreGraphAttributionRevision")
    dataset = dataset_model.objects.create(key="migration", payload=payload)
    node = node_model.objects.create(dataset=dataset, identity="LOCAL:dub", is_umbrella=False)
    current = {"decisionId": "current", "source": "fixture", "rationale": "current assignment"}
    historical = {"decisionId": "historical", "source": "fixture", "rationale": "previous assignment"}
    assignment_model.objects.create(track_id=song.pk, node=node, provenance=current)
    archived = history_model.objects.create(
        dataset=dataset,
        track_id=song.pk,
        graph_revision=dataset.revision,
        attributions={"LOCAL:dub": historical},
    )
    try:
        MigrationExecutor(connection).migrate(latest)
        assert set(GenreGraphEvidence.objects.filter(dataset_id=dataset.pk).values_list("decision_id", flat=True)) == {
            "current",
            "historical",
        }
        row = GenreGraphAttribution.objects.get(track=song)
        assert list(row.evidence.values_list("decision_id", flat=True)) == ["current"]
        assert GenreGraphAttributionRevision.objects.get(revision=archived.revision).attributions == {
            "LOCAL:dub": [historical]
        }
        assert GenreGraphAssignmentState.objects.filter(dataset_id=dataset.pk, track=song).exists()
    finally:
        MigrationExecutor(connection).migrate(latest)


def test_cold_1710_node_shared_ancestry_publication_uses_staged_closure():
    evidence = {"decisionId": "cold-shared", "source": "synthetic", "rationale": "Shared ancestry stress fixture"}
    parent_ids = [f"LOCAL:parent-{index}" for index in range(8)]
    leaf_ids = [f"LOCAL:leaf-{index}" for index in range(1701)]
    payload = {
        "contractVersion": 2,
        "curationExportedOn": "2026-11-14T00:00:00Z",
        "nodes": [
            {"id": identity, "name": identity, "kind": "genre", "canonicalState": "before_entry"}
            for identity in ["LOCAL:root", *parent_ids, *leaf_ids]
        ],
        "relations": [
            {"childId": child, "parentId": parent, "type": "classification", "provenance": evidence}
            for child, parent in [
                *((parent, "LOCAL:root") for parent in parent_ids),
                *((leaf, parent) for leaf in leaf_ids for parent in parent_ids),
            ]
        ],
        "boundaries": [],
    }
    dataset = replace_graph(key="cold-shared", payload=payload, expected_revision=None)
    assert dataset.nodes.count() == 1710
    assert dataset.access.count() == 1 + 8 * 2 + 1701 * 10
    song = Track(title="Shared leaf assignment")
    Track.objects.bulk_create([song])
    replace_track_attributions(
        key=dataset.pk,
        track_id=song.pk,
        attributions={identity: [evidence] for identity in leaf_ids[:2]},
        expected_revision=dataset.revision,
        expected_assignment_revision=None,
    )
    assert list(select_tracks(Track.objects.all(), key=dataset.pk, identity=parent_ids[0])) == [song]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT reltuples FROM pg_class WHERE oid = %s::regclass",
            [dataset.access.model._meta.db_table],
        )
        assert cursor.fetchone()[0] >= dataset.access.count()
    row_ids = set(dataset.access.values_list("pk", flat=True))
    payload["nodes"][-1]["name"] = "Metadata edit"
    replace_graph(key=dataset.pk, payload=payload, expected_revision=dataset.revision)
    assert set(dataset.access.values_list("pk", flat=True)) == row_ids


@pytest.mark.parametrize("mutation", ["insert", "update"])
def test_direct_assignment_rechecks_activity_after_concurrent_retirement(payload, mutation):
    dataset = replace_graph(key="reference", payload=payload, expected_revision=None)
    song = Track(title="Concurrent retirement")
    Track.objects.bulk_create([song])
    retiring = dataset.nodes.get(identity="LOCAL:french-dub")
    if mutation == "update":
        GenreGraphAttribution.objects.create(track=song, node=dataset.nodes.get(identity="LOCAL:dub"))
    attempted = Event()

    def assign():
        def mark_attempt(execute, sql, params, many, context):
            if sql.startswith(("INSERT", "UPDATE")):
                attempted.set()
            return execute(sql, params, many, context)

        try:
            with transaction.atomic(), connection.execute_wrapper(mark_attempt):
                if mutation == "insert":
                    GenreGraphAttribution.objects.create(track=song, node=retiring)
                else:
                    GenreGraphAttribution.objects.filter(track=song).update(node=retiring)
        except IntegrityError as error:
            assert "Invalid active graph reference" in str(error)
            return "rejected"
        return "committed"

    changed = deepcopy(payload)
    changed["nodes"] = [n for n in changed["nodes"] if n["id"] != retiring.identity]
    changed["relations"] = [
        r for r in changed["relations"] if r["childId"] != retiring.identity and r["parentId"] != retiring.identity
    ]
    with ThreadPoolExecutor(max_workers=1) as pool:
        with graph_write_transaction(key=dataset.key, expected_revision=dataset.revision):
            future = pool.submit(in_connection, assign)
            assert attempted.wait(timeout=10)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
            replace_graph(
                key=dataset.key,
                payload=changed,
                expected_revision=dataset.revision,
                retirements={
                    retiring.identity: {
                        "target": None,
                        "provenance": {
                            "decisionId": "concurrent-retirement",
                            "source": "fixture",
                            "rationale": "Retire explicitly",
                        },
                    }
                },
            )
        assert future.result(timeout=15) == "rejected"
    assert not GenreGraphAttribution.objects.filter(node__is_active=False).exists()


@pytest.mark.parametrize("mutation", ["insert", "update"])
def test_evidence_link_rechecks_dataset_after_concurrent_assignment_move(payload, mutation):
    source = replace_graph(key="source", payload=payload, expected_revision=None)
    target = replace_graph(key="target", payload=payload, expected_revision=None)
    song = Track(title="Concurrent evidence")
    Track.objects.bulk_create([song])
    assignment = GenreGraphAttribution.objects.create(track=song, node=source.nodes.get(identity="LOCAL:dub"))
    evidence = GenreGraphEvidence.objects.create(dataset=source, decision_id="race", source="fixture", rationale="test")
    link = None
    if mutation == "update":
        other = GenreGraphAttribution.objects.create(track=song, node=source.nodes.get(identity="LOCAL:french-dub"))
        link = GenreGraphAttributionEvidence.objects.create(attribution=other, evidence=evidence)
    attempted = Event()

    def attach():
        def mark_attempt(execute, sql, params, many, context):
            if sql.startswith(("INSERT", "UPDATE")):
                attempted.set()
            return execute(sql, params, many, context)

        try:
            with transaction.atomic(), connection.execute_wrapper(mark_attempt):
                if mutation == "insert":
                    GenreGraphAttributionEvidence.objects.create(attribution=assignment, evidence=evidence)
                else:
                    GenreGraphAttributionEvidence.objects.filter(pk=link.pk).update(attribution=assignment)
        except IntegrityError as error:
            assert "evidence dataset" in str(error)
            return "rejected"
        return "committed"

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            GenreGraphAttribution.objects.filter(pk=assignment.pk).update(node=target.nodes.get(identity="LOCAL:dub"))
            future = pool.submit(in_connection, attach)
            assert attempted.wait(timeout=10)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
        assert future.result(timeout=15) == "rejected"
    assert not GenreGraphAttributionEvidence.objects.filter(attribution=assignment).exists()


def test_generic_snapshot_nests_graph_reads_and_rejects_unowned_transactions(payload):
    dataset = replace_graph(key="reference", payload=payload, expected_revision=None)
    with graph_read_snapshot(), graph_read_transaction(key=dataset.key) as read:
        assert read.revision == dataset.revision
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_isolation")
            assert cursor.fetchone()[0] == "repeatable read"
            cursor.execute("SHOW transaction_read_only")
            assert cursor.fetchone()[0] == "on"
    with transaction.atomic(), pytest.raises(ValueError, match="outermost"), graph_read_snapshot():
        pass
