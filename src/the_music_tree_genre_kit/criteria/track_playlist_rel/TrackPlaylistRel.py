from django.db import models

from .AbstractTrackPlaylistRel import AbstractTrackPlaylistRel
from .Fields import Fields
from .TrackPlaylistRelManager import TrackPlaylistRelManager


class TrackPlaylistRel(AbstractTrackPlaylistRel):
    objects: TrackPlaylistRelManager = TrackPlaylistRelManager()

    class Meta:
        app_label = "the_music_tree_genre_kit"
        db_table = "the_music_tree_genre_kit_track_playlist_rel"
        indexes = [
            models.Index(fields=["user", Fields.PLAYLIST], name="tpr_user_playlist_idx"),
            models.Index(fields=["user", Fields.TRACK_INTERNAL], name="tpr_user_track_idx"),
        ]
