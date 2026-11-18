"""Evidence validation and reviewed single-track assignment changes."""

from collections.abc import Mapping
from uuid import UUID, uuid4

from django.db import transaction
from the_music_tree_genre_graph import GraphValidationError

from .models import (
    GenreGraphAssignmentState,
    GenreGraphAttribution,
    GenreGraphAttributionEvidence,
    GenreGraphAttributionRevision,
    GenreGraphEvidence,
)


def validate_evidence(value: object) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != {"decisionId", "source", "rationale"}
        or any(not isinstance(item, str) or not item.strip() for item in value.values())
        or len(value["decisionId"]) > 255
    ):
        raise GraphValidationError("Evidence requires decisionId, source and rationale")
    return value


def register_evidence(dataset, decisions) -> dict:
    """The dataset lock serializes decision registration with every publication."""
    requested = {}
    for value in decisions:
        evidence = validate_evidence(value)
        decision_id = evidence["decisionId"]
        if decision_id in requested and requested[decision_id] != evidence:
            raise GraphValidationError(f"Conflicting evidence for decisionId: {decision_id}")
        requested[decision_id] = evidence
    existing = {
        evidence.decision_id: evidence
        for evidence in GenreGraphEvidence.objects.filter(dataset=dataset, decision_id__in=requested)
    }
    for decision_id, evidence in existing.items():
        value = requested[decision_id]
        if (evidence.source, evidence.rationale) != (value["source"], value["rationale"]):
            raise GraphValidationError(f"Conflicting evidence for decisionId: {decision_id}")
    created = GenreGraphEvidence.objects.bulk_create(
        [
            GenreGraphEvidence(
                dataset=dataset, decision_id=decision_id, source=value["source"], rationale=value["rationale"]
            )
            for decision_id, value in requested.items()
            if decision_id not in existing
        ]
    )
    existing.update((evidence.decision_id, evidence) for evidence in created)
    return existing


def assignment_snapshot(*, dataset, track_id) -> dict:
    rows = GenreGraphAttribution.objects.filter(dataset=dataset, track_id=track_id).prefetch_related("evidence", "node")
    return {
        row.node.identity: [
            {"decisionId": evidence.decision_id, "source": evidence.source, "rationale": evidence.rationale}
            for evidence in sorted(row.evidence.all(), key=lambda item: item.decision_id)
        ]
        for row in rows
    }


def archive_assignments(*, dataset, track_id, revision, attributions):
    GenreGraphAttributionRevision.objects.get_or_create(
        revision=revision,
        defaults={
            "dataset": dataset,
            "track_id": track_id,
            "graph_revision": dataset.revision,
            "attributions": attributions,
        },
    )


@transaction.atomic
def replace_track_attributions(
    *,
    key: str,
    track_id: UUID,
    attributions: Mapping[str, list[dict]],
    expected_revision: UUID,
    expected_assignment_revision: UUID | None,
) -> UUID:
    """None creates an assignment set; every later edit requires its reviewed token."""
    from the_music_tree_genre_kit.track.Track import Track

    from .storage import GraphRevisionConflict, graph_write_transaction

    with graph_write_transaction(key=key, expected_revision=expected_revision) as dataset:
        track = Track.objects.select_for_update().get(pk=track_id)
        if track.user_id is not None:
            raise GraphValidationError("Reference graph attributions require an ownerless track")
        state = GenreGraphAssignmentState.objects.filter(dataset=dataset, track=track).first()
        if (state.revision if state else None) != expected_assignment_revision:
            raise GraphRevisionConflict("Track assignments changed; reload before assigning tracks")
        if len(attributions) > 1:
            raise GraphValidationError(f"A track holds at most one node per dataset; got {sorted(attributions)}")
        nodes = dict(dataset.nodes.filter(identity__in=attributions, is_active=True).values_list("identity", "pk"))
        unknown = set(attributions) - nodes.keys()
        if unknown:
            raise GraphValidationError(f"Unknown attribution nodes: {sorted(unknown)}")
        normalized = {}
        for identity, evidence in attributions.items():
            if not isinstance(evidence, list) or not evidence:
                raise GraphValidationError(f"A nonempty evidence list is required for {identity}")
            normalized[identity] = sorted(
                [validate_evidence(value) for value in evidence], key=lambda value: value["decisionId"]
            )
            if len({value["decisionId"] for value in normalized[identity]}) != len(evidence):
                raise GraphValidationError(f"Duplicate evidence decisionId for {identity}")
        registered = register_evidence(dataset, [value for evidence in normalized.values() for value in evidence])
        previous = assignment_snapshot(dataset=dataset, track_id=track_id)
        if state is None:
            state = GenreGraphAssignmentState.objects.create(dataset=dataset, track=track)
        archive_assignments(dataset=dataset, track_id=track_id, revision=state.revision, attributions=previous)
        if previous == normalized:
            return state.revision
        GenreGraphAttribution.objects.filter(track=track, dataset=dataset).delete()
        rows = GenreGraphAttribution.objects.bulk_create(
            [GenreGraphAttribution(track=track, dataset=dataset, node_id=nodes[identity]) for identity in normalized]
        )
        GenreGraphAttributionEvidence.objects.bulk_create(
            [
                GenreGraphAttributionEvidence(attribution=row, evidence=registered[value["decisionId"]])
                for row, evidence in zip(rows, normalized.values(), strict=True)
                for value in evidence
            ]
        )
        # Empty sets still change the CAS token. DB guards also invalidate direct SQL mutations.
        state.revision = uuid4()
        state.save(update_fields=["revision"])
        archive_assignments(dataset=dataset, track_id=track_id, revision=state.revision, attributions=normalized)
        return state.revision


@transaction.atomic
def restore_track_attributions(
    *,
    key: str,
    track_id: UUID,
    revision: UUID,
    expected_revision: UUID,
    expected_assignment_revision: UUID | None,
) -> UUID:
    """Restore an archived set only onto a surviving track and active identities."""
    archived = GenreGraphAttributionRevision.objects.get(dataset_id=key, track_id=track_id, revision=revision)
    return replace_track_attributions(
        key=key,
        track_id=track_id,
        attributions=archived.attributions,
        expected_revision=expected_revision,
        expected_assignment_revision=expected_assignment_revision,
    )
