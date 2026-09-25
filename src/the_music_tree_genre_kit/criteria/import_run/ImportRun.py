from django.conf import settings
from django.db import models
from the_music_tree_api_kit.field.AppCharField import AppCharField


class ImportRun(models.Model):
    """
    One applied `import_criteria_tree` call. Every pipeline row the run's payload
    contains gets `last_seen_run` pointed at it; pipeline rows left on an older run
    are stale. A failed import rolls back with its transaction, so only succeeded
    runs persist.
    """

    class Status(models.TextChoices):
        RUNNING = "running"
        SUCCEEDED = "succeeded"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = AppCharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    deleted_count = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "the_music_tree_genre_kit"
