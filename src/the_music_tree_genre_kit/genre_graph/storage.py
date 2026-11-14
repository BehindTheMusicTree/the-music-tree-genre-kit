"""Transactional graph replacement and SQL catalogue selection.

The payload is authoritative. Relational nodes and access rows are its index,
rebuilt in the same transaction; track attributions keep stable node keys.
"""

from collections.abc import Mapping
from contextlib import contextmanager
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import Exists, OuterRef, QuerySet

from .graph import GenreGraph, GraphValidationError
from .models import (
    GenreGraphAccess,
    GenreGraphAttribution,
    GenreGraphAttributionRevision,
    GenreGraphDataset,
    GenreGraphNode,
    GenreGraphRevision,
)


class GraphRevisionConflict(GraphValidationError):
    """A concurrent writer changed the graph the caller reviewed."""


@transaction.atomic
def replace_graph(*, key: str, payload: dict, expected_revision: UUID | None) -> GenreGraphDataset:
    """Create explicitly or replace a reviewed revision, retaining rollback artifacts.

    None means create-only, never overwrite an existing graph. A removed node
    with attributions is protected until the consumer supplies an explicit mapping.
    """
    if not key or len(key) > GenreGraphDataset._meta.get_field("key").max_length:
        raise GraphValidationError("A nonempty graph dataset key of at most 64 characters is required")
    graph = GenreGraph(payload)
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
            return dataset
        dataset.revision = uuid4()
        dataset.membership_revision = uuid4()
        dataset.payload = graph.to_payload()
        dataset.save(update_fields=["revision", "membership_revision", "payload"])
    GenreGraphRevision.objects.create(dataset=dataset, revision=dataset.revision, payload=dataset.payload)
    existing = {node.identity: node for node in dataset.nodes.all()}
    stale = set(existing) - graph.node_ids
    dataset.nodes.filter(identity__in=stale).delete()
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
        node.is_umbrella = graph.node(identity).get("isUmbrella", False)
        node.canonical_state = graph.node(identity).get("canonicalState")
        updated.append(node)
    GenreGraphNode.objects.bulk_update(updated, ["is_umbrella", "canonical_state"])
    nodes = {node.identity: node for node in dataset.nodes.all()}
    GenreGraphAccess.objects.filter(ancestor__dataset=dataset).delete()
    batch = []
    for identity, node in nodes.items():
        scopes = ("all", "canonical", "regional") if node.canonical_state == "canonical" else ("all",)
        for scope in scopes:
            for descendant in graph.selected_nodes(identity, scope=scope):
                batch.append(GenreGraphAccess(ancestor=node, descendant=nodes[descendant], scope=scope))
                if len(batch) >= 1000:
                    GenreGraphAccess.objects.bulk_create(batch)
                    batch.clear()
    GenreGraphAccess.objects.bulk_create(batch)
    return dataset


@contextmanager
def graph_read_transaction(*, key: str):
    """Keep several queries and their revision tokens on one committed graph.

    Evaluate lazy querysets inside this context. Writers take the same dataset
    lock, so READ COMMITTED cannot mix metadata from one graph with another's
    selection index. Keep the context short; it serializes writers and readers.
    """
    with transaction.atomic():
        yield GenreGraphDataset.objects.select_for_update().get(pk=key)


@contextmanager
def graph_write_transaction(*, key: str, expected_revision: UUID):
    """Lock a reviewed dataset before bulk attribution writes or track deletion.

    Enter before locking tracks or attribution rows. Database invalidation
    triggers take the dataset lock too; taking it last can deadlock a service
    writer that already holds it. For multiple datasets, enter in key order.
    """
    with graph_read_transaction(key=key) as dataset:
        if dataset.revision != expected_revision:
            raise GraphRevisionConflict(f"Graph revision changed for {key}; reload before writing tracks")
        yield dataset


@transaction.atomic
def restore_graph(*, key: str, revision: UUID, expected_revision: UUID) -> GenreGraphDataset:
    archived = GenreGraphRevision.objects.get(dataset_id=key, revision=revision)
    return replace_graph(key=key, payload=archived.payload, expected_revision=expected_revision)


def effective_attributions(*, key: str) -> QuerySet:
    """Normalize direct assignments in SQL without materializing track populations."""
    more_precise = GenreGraphAttribution.objects.filter(
        track_id=OuterRef("track_id"),
        node__dataset_id=key,
        node__inclusive_ancestors__ancestor_id=OuterRef("node_id"),
        node__inclusive_ancestors__scope="all",
    ).exclude(node_id=OuterRef("node_id"))
    return GenreGraphAttribution.objects.filter(node__dataset_id=key).filter(~Exists(more_precise))


def select_tracks(
    tracks: QuerySet, *, key: str, identity: str, scope: str = "all", include_descendants: bool = True
) -> QuerySet:
    GenreGraphDataset.objects.get(pk=key)
    node = GenreGraphNode.objects.get(dataset_id=key, identity=identity)
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


@transaction.atomic
def replace_track_attributions(
    *, key: str, track_id: UUID, attributions: Mapping[str, dict], expected_revision: UUID
) -> None:
    """Replace one reference track's explicit assignments without guessing regions."""
    from the_music_tree_genre_kit.track.Track import Track

    dataset = GenreGraphDataset.objects.select_for_update().get(pk=key)
    if dataset.revision != expected_revision:
        raise GraphRevisionConflict(f"Graph revision changed for {key}; reload before assigning tracks")
    track = Track.objects.select_for_update().get(pk=track_id)
    if track.user_id is not None:
        raise GraphValidationError("Reference graph attributions require an ownerless track")
    nodes = dict(dataset.nodes.filter(identity__in=attributions).values_list("identity", "pk"))
    unknown = set(attributions) - nodes.keys()
    if unknown:
        raise GraphValidationError(f"Unknown attribution nodes: {sorted(unknown)}")
    for identity, provenance in attributions.items():
        if (
            not isinstance(provenance, dict)
            or set(provenance) != {"decisionId", "source", "rationale"}
            or any(not isinstance(value, str) or not value.strip() for value in provenance.values())
        ):
            raise GraphValidationError(f"Attribution provenance is required for {identity}")
    previous = dict(
        GenreGraphAttribution.objects.filter(track=track, node__dataset=dataset).values_list(
            "node__identity", "provenance"
        )
    )
    if previous == attributions:
        return
    history = GenreGraphAttributionRevision.objects.filter(dataset=dataset, track_id=track_id)
    latest = history.order_by("-created_at").first()
    if latest is None or latest.attributions != previous:
        GenreGraphAttributionRevision.objects.create(
            dataset=dataset, track_id=track_id, graph_revision=dataset.revision, attributions=previous
        )
    GenreGraphAttribution.objects.filter(track=track, node__dataset=dataset).delete()
    GenreGraphAttribution.objects.bulk_create(
        [
            GenreGraphAttribution(track=track, node_id=nodes[identity], provenance=provenance)
            for identity, provenance in attributions.items()
        ]
    )
    GenreGraphAttributionRevision.objects.create(
        dataset=dataset, track_id=track_id, graph_revision=dataset.revision, attributions=dict(attributions)
    )


@transaction.atomic
def restore_track_attributions(*, key: str, track_id: UUID, revision: UUID, expected_revision: UUID) -> None:
    """Restore reviewed assignments after restoring any required graph concepts.

    No fallback to surviving nodes: missing identities reject the whole restore.
    Tracks remain consumer-owned; this operation never recreates a deleted track.
    """
    archived = GenreGraphAttributionRevision.objects.get(dataset_id=key, track_id=track_id, revision=revision)
    replace_track_attributions(
        key=key, track_id=track_id, attributions=archived.attributions, expected_revision=expected_revision
    )
