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
        ]
