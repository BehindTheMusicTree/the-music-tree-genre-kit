from typing import TYPE_CHECKING, cast

from django.db import models
from the_music_tree_api_kit.trackable_play_count.TrackablePlayCount import TrackablePlayCount

from the_music_tree_genre_kit.track_mixin.TrackMixin import TrackMixin

from .Fields import Fields
from .PlaylistManager import PlaylistManager

if TYPE_CHECKING:
    from the_music_tree_genre_kit.criteria.track_playlist_rel.AbstractTrackPlaylistRel import AbstractTrackPlaylistRel
    from the_music_tree_genre_kit.track.Track import Track


class Playlist(TrackMixin, TrackablePlayCount):
    objects: PlaylistManager = PlaylistManager()

    if TYPE_CHECKING:
        track_playlist_rels: models.QuerySet[AbstractTrackPlaylistRel]
        manual_playlist: models.Model | None
        criteria_playlist: models.Model | None

    class Meta:
        app_label = "the_music_tree_genre_kit"
        indexes = [models.Index(fields=["user", Fields.UUID], name="playlist_user_uuid_idx")]

    def __str__(self) -> str:
        return f"{self.uuid} | {self.name}"

    @property
    def tracks(self) -> models.QuerySet[Track]:
        return getattr(self, Fields.TRACKS_RELATED_NAME)

    @property
    def type_label(self) -> str:
        if hasattr(self, Fields.MANUAL_PLAYLIST):
            if not self.manual_playlist:
                raise ValueError("Playlist has no manual playlist")
            return self.manual_playlist.type_label
        if hasattr(self, Fields.CRITERIA_PLAYLIST):
            if not self.criteria_playlist:
                raise ValueError("Playlist has no criteria playlist")
            return self.criteria_playlist.type_label
        raise ValueError("Playlist has no type")

    @property
    def tracks_not_archived_dict_by_position(self) -> dict[int | None, Track]:
        return Playlist.objects.get_ordered_relations_for_playlist(self)

    @property
    def name(self) -> str:
        if hasattr(self, Fields.MANUAL_PLAYLIST):
            if not self.manual_playlist:
                raise ValueError("Playlist has no manual playlist")
            return cast(str, self.manual_playlist.name)
        if hasattr(self, Fields.CRITERIA_PLAYLIST):
            if not self.criteria_playlist:
                raise ValueError("Playlist has no criteria playlist")
            return cast(str, self.criteria_playlist.name)
        raise ValueError("Playlist has no name")
