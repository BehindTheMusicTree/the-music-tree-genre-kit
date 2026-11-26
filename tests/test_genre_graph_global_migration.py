"""Migration 0026 converts stored contract 4 graphs in place and leaves their database guards standing."""

from uuid import uuid4

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from the_music_tree_genre_graph import GenreGraph

APP = "the_music_tree_genre_kit"
BEFORE = (APP, "0025_staged_publication_bypass")
AFTER = (APP, "0026_global_three_relations")
EVIDENCE = {"decisionId": "migration", "source": "fixture", "rationale": "contract migration"}


def payload_v4():
    return {
        "contractVersion": 4,
        "curationExportedOn": "2026-11-14T00:00:00Z",
        "nodes": [
            {"id": "LOCAL:dub", "name": "Dub", "kind": "genre"},
            {"id": "LOCAL:french-dub", "name": "French dub", "kind": "genre"},
            {
                "id": "LOCAL:world",
                "name": "World",
                "kind": "overview",
                "isUmbrella": True,
                "overviewType": "current",
                "overviewProvenance": EVIDENCE,
            },
            {
                "id": "LOCAL:france",
                "name": "France",
                "kind": "overview",
                "isUmbrella": True,
                "overviewType": "current",
                "overviewProvenance": EVIDENCE,
            },
        ],
        "relations": [
            {"childId": child, "parentId": parent, "type": kind, "provenance": EVIDENCE}
            for child, parent, kind in [
                ("LOCAL:french-dub", "LOCAL:dub", "classification"),
                ("LOCAL:french-dub", "LOCAL:france", "regional_membership"),
                ("LOCAL:france", "LOCAL:world", "regional_membership"),
            ]
        ],
        "canonicalRoots": [{"nodeId": "LOCAL:dub", "provenance": EVIDENCE}],
    }


def payload_v5():
    payload = payload_v4()
    payload["contractVersion"] = 5
    payload["globalRoots"] = payload.pop("canonicalRoots")
    for relation in payload["relations"]:
        relation["type"] = "classification"
    return payload


def migrate(target):
    """Return the historical models at ``target``."""
    MigrationExecutor(connection).migrate([target])
    return MigrationExecutor(connection).loader.project_state(target).apps


@pytest.mark.django_db(transaction=True)
def test_contract_5_migration_converts_stored_graphs_and_keeps_guards():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        old = migrate(BEFORE)
        dataset = old.get_model(APP, "GenreGraphDataset").objects.create(key="contract", payload=payload_v4())
        revision = uuid4()
        old.get_model(APP, "GenreGraphRevision").objects.create(
            dataset=dataset, revision=revision, payload=payload_v4()
        )
        older = {"contractVersion": 3, "canonicalRoots": []}
        old.get_model(APP, "GenreGraphDataset").objects.create(key="older", payload=older)
        old.get_model(APP, "GenreGraphNode").objects.create(
            dataset=dataset, identity="LOCAL:dub", is_umbrella=False, canonical_state="canonical"
        )

        new = migrate(AFTER)
        stored = new.get_model(APP, "GenreGraphDataset").objects.get(pk="contract")
        archived = new.get_model(APP, "GenreGraphRevision").objects.get(revision=revision)
        assert stored.payload == archived.payload == payload_v5()
        assert (stored.revision, stored.membership_revision) == (dataset.revision, dataset.membership_revision)
        assert new.get_model(APP, "GenreGraphDataset").objects.get(pk="older").payload == older
        assert GenreGraph(stored.payload).state("LOCAL:dub") == "global"
        node = new.get_model(APP, "GenreGraphNode").objects.get(dataset_id="contract")
        assert node.state == "global"
        with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
            new.get_model(APP, "GenreGraphRevision").objects.update(payload={})
        with pytest.raises(IntegrityError, match="identity is immutable"), transaction.atomic():
            new.get_model(APP, "GenreGraphNode").objects.update(identity="LOCAL:other")

        old = migrate(BEFORE)
        assert old.get_model(APP, "GenreGraphDataset").objects.get(pk="contract").payload == payload_v4()
        assert old.get_model(APP, "GenreGraphDataset").objects.get(pk="older").payload == older
        assert old.get_model(APP, "GenreGraphRevision").objects.get(revision=revision).payload == payload_v4()
        assert old.get_model(APP, "GenreGraphNode").objects.get(dataset_id="contract").canonical_state == "canonical"
        with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
            old.get_model(APP, "GenreGraphRevision").objects.update(payload={})
    finally:
        # Audit rows reject DELETE, which the transactional flush needs: empty them by unwinding the graph tables.
        executor = MigrationExecutor(connection)
        executor.recorder.record_unapplied(APP, "0024_restrict_regional_access")
        MigrationExecutor(connection).migrate([(APP, "0015_trackplaylistrel_playlist_genre_pos_idx")])
        MigrationExecutor(connection).migrate(latest)
