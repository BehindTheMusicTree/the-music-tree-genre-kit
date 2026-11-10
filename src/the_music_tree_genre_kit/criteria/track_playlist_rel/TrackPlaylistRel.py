from django.conf import settings
from django.db import models
from the_music_tree_api_kit.field.foreign_key.PrivateForeignKey import PrivateForeignKey

from .AbstractTrackPlaylistRel import AbstractTrackPlaylistRel
from .Fields import Fields
from .TrackPlaylistRelManager import TrackPlaylistRelManager


class TrackPlaylistRel(AbstractTrackPlaylistRel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="%(class)ss", null=True, blank=True
    )

    # Denormalised copy of `track.genre`, kept by the consuming app. It lets a playlist's membership be filtered by
    # genre from this table alone, instead of probing the 30M-row track table once per member.
    genre = PrivateForeignKey(
        settings.CRITERIA_MODEL,
        on_delete=models.DO_NOTHING,
        db_index=False,
        null=True,
        blank=True,
        related_name="track_playlist_rels_of_genre",
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
            models.Index(fields=[Fields.PLAYLIST, "genre", "position", "id"], name="tpr_playlist_genre_pos_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=[Fields.PLAYLIST, Fields.TRACK_INTERNAL], name="uniq_track_playlist_rel"),
        ]
