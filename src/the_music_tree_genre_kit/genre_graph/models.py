"""Reference graph storage, separate from consumers' personal criteria trees."""

from uuid import uuid4

from django.db import models


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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "the_music_tree_genre_kit"


class GenreGraphNode(models.Model):
    dataset = models.ForeignKey(GenreGraphDataset, on_delete=models.CASCADE, related_name="nodes")
    identity = models.CharField(max_length=255)
    is_umbrella = models.BooleanField()
    canonical_state = models.CharField(max_length=16, null=True)

    class Meta:
        app_label = "the_music_tree_genre_kit"
        constraints = [models.UniqueConstraint(fields=["dataset", "identity"], name="graph_node_identity_unique")]


class GenreGraphAccess(models.Model):
    """Materialized selection by scope, including the selected node itself."""

    ancestor = models.ForeignKey(GenreGraphNode, on_delete=models.CASCADE, related_name="inclusive_descendants")
    descendant = models.ForeignKey(GenreGraphNode, on_delete=models.CASCADE, related_name="inclusive_ancestors")
    scope = models.CharField(max_length=16)

    class Meta:
        app_label = "the_music_tree_genre_kit"
        constraints = [
            models.UniqueConstraint(fields=["ancestor", "scope", "descendant"], name="graph_access_unique"),
            models.CheckConstraint(
                condition=models.Q(scope__in=["all", "canonical", "regional"]), name="graph_access_scope"
            ),
        ]


class GenreGraphAttribution(models.Model):
    """Explicit reference-catalogue attribution; deleting a concept cannot erase it."""

    track = models.ForeignKey(
        "the_music_tree_genre_kit.Track", on_delete=models.CASCADE, related_name="graph_attributions"
    )
    node = models.ForeignKey(GenreGraphNode, on_delete=models.PROTECT, related_name="attributions")
    provenance = models.JSONField()

    class Meta:
        app_label = "the_music_tree_genre_kit"
        constraints = [models.UniqueConstraint(fields=["track", "node"], name="graph_attribution_unique")]


class GenreGraphAttributionRevision(models.Model):
    """Restorable assignment snapshots; semantic keys survive graph replacement."""

    revision = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    dataset = models.ForeignKey(GenreGraphDataset, on_delete=models.CASCADE, related_name="attribution_history")
    track_id = models.UUIDField(db_index=True)
    graph_revision = models.UUIDField()
    attributions = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "the_music_tree_genre_kit"
