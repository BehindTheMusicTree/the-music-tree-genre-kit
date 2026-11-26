"""Reference graph storage, separate from consumers' personal criteria trees."""

from enum import StrEnum
from uuid import uuid4

from django.db import models


class GraphScope(StrEnum):
    """Which descendants a selection reaches: restricted, every one (extended), or only the expressions."""

    RESTRICTED = "restricted"
    EXTENDED = "extended"
    EXPRESSIONS = "expressions"


class GenreGraphDataset(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    revision = models.UUIDField(default=uuid4, editable=False)
    membership_revision = models.UUIDField(default=uuid4, editable=False)
    payload = models.JSONField()

    class Meta:
        app_label = "the_music_tree_genre_kit"


class GenreGraphRevision(models.Model):
    revision = models.UUIDField(primary_key=True, editable=False)
    dataset = models.ForeignKey(GenreGraphDataset, on_delete=models.CASCADE, related_name="history")
    payload = models.JSONField()
    retirements = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "the_music_tree_genre_kit"


class GenreGraphNode(models.Model):
    dataset = models.ForeignKey(GenreGraphDataset, on_delete=models.CASCADE, related_name="nodes")
    identity = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_umbrella = models.BooleanField()
    state = models.CharField(max_length=16, null=True)

    class Meta:
        app_label = "the_music_tree_genre_kit"
        constraints = [
            models.UniqueConstraint(fields=["dataset", "identity"], name="graph_node_identity_unique"),
            models.UniqueConstraint(fields=["dataset", "id"], name="graph_node_dataset_id_unique"),
        ]


class GenreGraphAccess(models.Model):
    """Materialized selection by scope, including the selected node itself."""

    dataset = models.ForeignKey(GenreGraphDataset, on_delete=models.CASCADE, related_name="access")
    ancestor = models.ForeignKey(GenreGraphNode, on_delete=models.CASCADE, related_name="inclusive_descendants")
    descendant = models.ForeignKey(GenreGraphNode, on_delete=models.CASCADE, related_name="inclusive_ancestors")
    scope = models.CharField(max_length=16)

    class Meta:
        app_label = "the_music_tree_genre_kit"
        indexes = [
            models.Index(fields=["dataset", "ancestor", "scope", "descendant"], name="graph_access_forward"),
            models.Index(fields=["dataset", "descendant", "scope", "ancestor"], name="graph_access_reverse"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["ancestor", "scope", "descendant"], name="graph_access_unique"),
            models.CheckConstraint(
                condition=models.Q(scope__in=[scope.value for scope in GraphScope]), name="graph_access_scope"
            ),
        ]


class GenreGraphAttribution(models.Model):
    """Explicit reference-catalogue attribution; deleting a concept cannot erase it."""

    track = models.ForeignKey(
        "the_music_tree_genre_kit.Track", on_delete=models.CASCADE, related_name="graph_attributions"
    )
    node = models.ForeignKey(GenreGraphNode, on_delete=models.PROTECT, related_name="attributions")
    # Denormalized from node and immutable: database guards pin it to the node's dataset, so a
    # track holds at most one node per dataset without a join.
    dataset = models.ForeignKey(GenreGraphDataset, on_delete=models.PROTECT, related_name="attributions")
    evidence = models.ManyToManyField("GenreGraphEvidence", through="GenreGraphAttributionEvidence")

    class Meta:
        app_label = "the_music_tree_genre_kit"
        constraints = [
            models.UniqueConstraint(fields=["dataset", "track"], name="graph_attribution_dataset_track_unique")
        ]


class GenreGraphAttributionRevision(models.Model):
    """Restorable assignment snapshots; semantic keys survive graph replacement.

    Append-only audit: migration 0021 triggers reject UPDATE and DELETE. A snapshot therefore
    outlives its track, which is why `track_id` is deliberately not a foreign key; restoration
    only targets surviving tracks. Pruning history is a retention decision, not a cascade.
    """

    revision = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    dataset = models.ForeignKey(GenreGraphDataset, on_delete=models.CASCADE, related_name="attribution_history")
    track_id = models.UUIDField(db_index=True)
    graph_revision = models.UUIDField()
    attributions = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "the_music_tree_genre_kit"


class GenreGraphEvidence(models.Model):
    """A dataset decision has permanent content, shared by all assignments citing it."""

    dataset = models.ForeignKey(GenreGraphDataset, on_delete=models.PROTECT)
    decision_id = models.CharField(max_length=255)
    source = models.TextField()
    rationale = models.TextField()

    class Meta:
        app_label = "the_music_tree_genre_kit"
        constraints = [
            models.UniqueConstraint(fields=["dataset", "decision_id"], name="graph_evidence_decision_unique")
        ]


class GenreGraphAttributionEvidence(models.Model):
    attribution = models.ForeignKey(GenreGraphAttribution, on_delete=models.CASCADE)
    evidence = models.ForeignKey(GenreGraphEvidence, on_delete=models.PROTECT)

    class Meta:
        app_label = "the_music_tree_genre_kit"
        constraints = [
            models.UniqueConstraint(fields=["attribution", "evidence"], name="graph_attribution_evidence_unique")
        ]


class GenreGraphAssignmentState(models.Model):
    """CAS token survives clearing assignments; a deleted track cannot be restored."""

    dataset = models.ForeignKey(GenreGraphDataset, on_delete=models.CASCADE)
    track = models.ForeignKey("the_music_tree_genre_kit.Track", on_delete=models.CASCADE)
    revision = models.UUIDField(default=uuid4, editable=False)

    class Meta:
        app_label = "the_music_tree_genre_kit"
        constraints = [models.UniqueConstraint(fields=["dataset", "track"], name="graph_assignment_state_unique")]
