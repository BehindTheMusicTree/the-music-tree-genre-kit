"""Transactional graph replacement and SQL catalogue selection.

The payload is authoritative. Relational nodes and access rows are its index,
rebuilt in the same transaction; track attributions keep stable node keys.
"""

from collections.abc import Mapping
from contextlib import contextmanager
from uuid import UUID, uuid4

from django.db import connection, transaction
from django.db.models import Exists, OuterRef, QuerySet
from the_music_tree_genre_graph import GenreGraph, GraphValidationError

from .assignments import replace_track_attributions, restore_track_attributions, validate_evidence
from .closure import analyze_nodes, replace_access
from .models import (
    GenreGraphAccess,
    GenreGraphAttribution,
    GenreGraphDataset,
    GenreGraphNode,
    GenreGraphRevision,
)
from .retirements import remap_retirements


class GraphRevisionConflict(GraphValidationError):
    """A concurrent writer changed the graph the caller reviewed."""


def require_graph_write_context():
    if connection.vendor not in {"postgresql", "sqlite"}:
        raise GraphValidationError("Reference graphs require PostgreSQL or SQLite")
    if getattr(connection, "graph_snapshot_depth", 0):
        raise GraphValidationError("Cannot write inside a graph read snapshot")
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_isolation")
            if cursor.fetchone()[0] != "read committed":
                raise GraphValidationError("Graph writes require READ COMMITTED isolation")


@transaction.atomic
def replace_graph(
    *, key: str, payload: dict, expected_revision: UUID | None, retirements: Mapping | None = None
) -> GenreGraphDataset:
    """Create explicitly or replace a reviewed revision, retaining rollback artifacts.

    None means create-only, never overwrite an existing graph. A removed node
    requires an explicit retirement decision, even when it has no attributions.
    """
    if not key or len(key) > GenreGraphDataset._meta.get_field("key").max_length:
        raise GraphValidationError("A nonempty graph dataset key of at most 64 characters is required")
    require_graph_write_context()
    graph = GenreGraph(payload)
    previous_revision = expected_revision
    if expected_revision is None:
        # The unique key arbitrates simultaneous first imports. get_or_create
        # handles the losing insert in a savepoint without breaking our transaction.
        dataset, created = GenreGraphDataset.objects.select_for_update().get_or_create(
            key=key, defaults={"payload": graph.to_payload()}
        )
        if not created:
            raise GraphRevisionConflict(f"Graph dataset already exists: {key}")
    else:
        try:
            dataset = GenreGraphDataset.objects.select_for_update().get(pk=key)
        except GenreGraphDataset.DoesNotExist as error:
            raise GraphRevisionConflict(f"Graph dataset does not exist: {key}") from error
        if expected_revision != dataset.revision:
            raise GraphRevisionConflict(f"Graph revision changed for {key}; reload before replacing it")
        if dataset.payload == graph.to_payload():
            if retirements:
                raise GraphValidationError("Unchanged graphs cannot retire identities")
            return dataset
        dataset.revision = uuid4()
        dataset.membership_revision = uuid4()
        dataset.payload = graph.to_payload()
        dataset.save(update_fields=["revision", "membership_revision", "payload"])
    existing = {node.identity: node for node in dataset.nodes.all()}
    stale = {identity for identity, node in existing.items() if node.is_active} - graph.node_ids
    decisions = {} if retirements is None else retirements
    if set(decisions) != stale:
        raise GraphValidationError("Retirements must name every removed identity exactly once")
    for identity, decision in decisions.items():
        if not isinstance(decision, dict) or set(decision) != {"target", "provenance"}:
            raise GraphValidationError(f"Explicit retirement target and provenance required: {identity}")
        if decision["target"] is not None and decision["target"] not in graph.node_ids:
            raise GraphValidationError(f"Retirement target must remain active: {identity}")
        validate_evidence(decision["provenance"])
    GenreGraphRevision.objects.create(
        dataset=dataset, revision=dataset.revision, payload=dataset.payload, retirements=dict(decisions)
    )
    created = [
        GenreGraphNode(
            dataset=dataset,
            identity=identity,
            is_umbrella=graph.node(identity).get("isUmbrella", False),
            canonical_state=graph.node(identity).get("canonicalState"),
        )
        for identity in sorted(graph.node_ids - existing.keys())
    ]
    GenreGraphNode.objects.bulk_create(created)
    updated = []
    for identity in graph.node_ids & existing.keys():
        node = existing[identity]
        umbrella = graph.node(identity).get("isUmbrella", False)
        state = graph.node(identity).get("canonicalState")
        if (node.is_active, node.is_umbrella, node.canonical_state) != (True, umbrella, state):
            node.is_active = True
            node.is_umbrella = umbrella
            node.canonical_state = state
            updated.append(node)
    GenreGraphNode.objects.bulk_update(updated, ["is_active", "is_umbrella", "canonical_state"])
    nodes = {node.identity: node for node in dataset.nodes.all()}
    remap_retirements(dataset=dataset, decisions=decisions, nodes=nodes, previous_revision=previous_revision)
    retired_count = dataset.nodes.filter(identity__in=stale).update(is_active=False)
    nodes = {identity: node for identity, node in nodes.items() if identity in graph.node_ids}
    if created or updated or retired_count:
        analyze_nodes()
    replace_access(dataset, graph, nodes)
    dataset.refresh_from_db(fields=["membership_revision"])
    return dataset


@contextmanager
def graph_read_snapshot():
    """Materialize response data inside one outermost read-only snapshot."""
    nested = getattr(connection, "graph_snapshot_depth", 0)
    if connection.vendor not in {"postgresql", "sqlite"}:
        raise GraphValidationError("Reference graphs require PostgreSQL or SQLite")
    if connection.vendor == "postgresql" and connection.in_atomic_block and not nested:
        raise GraphValidationError("Graph reads require an outermost REPEATABLE READ snapshot")
    if nested:
        yield
        return
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.graph_snapshot_depth = nested + 1
        try:
            yield
        finally:
            connection.graph_snapshot_depth = nested


@contextmanager
def graph_read_transaction(*, key: str):
    """Read a dataset and its response data in the same snapshot."""
    with graph_read_snapshot():
        yield GenreGraphDataset.objects.get(pk=key)


@contextmanager
def graph_write_transaction(*, key: str, expected_revision: UUID):
    """Lock datasets in key order after the consumer source gate, before tracks."""
    with transaction.atomic():
        require_graph_write_context()
        dataset = GenreGraphDataset.objects.select_for_update().get(pk=key)
        if dataset.revision != expected_revision:
            raise GraphRevisionConflict(f"Graph revision changed for {key}; reload before writing tracks")
        yield dataset


@transaction.atomic
def restore_graph(
    *, key: str, revision: UUID, expected_revision: UUID, retirements: Mapping | None = None
) -> GenreGraphDataset:
    archived = GenreGraphRevision.objects.get(dataset_id=key, revision=revision)
    return replace_graph(
        key=key, payload=archived.payload, expected_revision=expected_revision, retirements=retirements
    )


def effective_attributions(*, key: str) -> QuerySet:
    """Normalize direct assignments in SQL without materializing track populations."""
    more_precise = GenreGraphAttribution.objects.filter(
        track_id=OuterRef("track_id"),
        node__dataset_id=key,
        node__inclusive_ancestors__ancestor_id=OuterRef("node_id"),
        node__inclusive_ancestors__scope="all",
    ).exclude(node_id=OuterRef("node_id"))
    return GenreGraphAttribution.objects.filter(node__dataset_id=key, node__is_active=True).filter(
        ~Exists(more_precise)
    )


def select_tracks(
    tracks: QuerySet, *, key: str, identity: str, scope: str = "all", include_descendants: bool = True
) -> QuerySet:
    GenreGraphDataset.objects.get(pk=key)
    node = GenreGraphNode.objects.get(dataset_id=key, identity=identity, is_active=True)
    if scope not in {"all", "canonical", "regional"} or (node.canonical_state != "canonical" and scope != "all"):
        raise GraphValidationError(f"Invalid selection scope {scope} for {identity}")
    attributions = effective_attributions(key=key)
    if include_descendants:
        attributions = attributions.filter(
            node__inclusive_ancestors__ancestor__dataset_id=key,
            node__inclusive_ancestors__ancestor__identity=identity,
            node__inclusive_ancestors__scope=scope,
        )
    else:
        attributions = attributions.filter(node__identity=identity)
    return tracks.filter(pk__in=attributions.values("track_id"))


def tracks_needing_refinement(tracks: QuerySet, *, key: str) -> QuerySet:
    attributions = effective_attributions(key=key).filter(node__is_umbrella=True)
    return tracks.filter(pk__in=attributions.values("track_id"))
