from django.conf import settings
from django.db import models

from .AbstractTrackPlaylistRel import AbstractTrackPlaylistRel
from .Fields import Fields
from .TrackPlaylistRelManager import TrackPlaylistRelManager


class TrackPlaylistRel(AbstractTrackPlaylistRel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="%(class)ss", null=True, blank=True
    )

    objects: TrackPlaylistRelManager = TrackPlaylistRelManager()

    class Meta:
        app_label = "the_music_tree_genre_kit"
        db_table = "the_music_tree_genre_kit_track_playlist_rel"
        indexes = [
            models.Index(fields=["user", Fields.PLAYLIST], name="tpr_user_playlist_idx"),
            models.Index(fields=["user", Fields.TRACK_INTERNAL], name="tpr_user_track_idx"),
            # Serves `ORDER BY position NULLS LAST, id` per playlist (btree ASC is NULLS LAST), so a tracks page walks
            # the index and stops at its LIMIT instead of sorting every member.
            models.Index(fields=[Fields.PLAYLIST, "position", "id"], name="tpr_playlist_position_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=[Fields.PLAYLIST, Fields.TRACK_INTERNAL], name="uniq_track_playlist_rel"),
        ]
