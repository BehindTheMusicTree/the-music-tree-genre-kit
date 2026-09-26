from typing import Any, TypeVar

from django.db.models import F, QuerySet
from the_music_tree_api_kit.public_standard_resource.StandardResourceManager import StandardResourceManager

from .AbstractTrackPlaylistRel import AbstractTrackPlaylistRel
from .Fields import Fields

T = TypeVar("T", bound=AbstractTrackPlaylistRel)


class AbstractTrackPlaylistRelManager(StandardResourceManager[T]):
    """
    Owns the position-bookkeeping and move logic shared by
    every app's concrete track-playlist relation manager. Fully concrete: the
    only historical divergence between apps was field/method naming, which is
    resolved by unifying the concrete rel model's field names.
    """

    def _decrement_positions_of_following_tracks(self, playlist: Any, position: int) -> None:
        self.filter(user=playlist.user, playlist=playlist, **{f"{Fields.POSITION}__gt": position}).update(
            position=F(Fields.POSITION) - 1
        )

    def _increment_positions_of_following_tracks(self, playlist: Any, position: int) -> None:
        self.filter(user=playlist.user, playlist=playlist, **{f"{Fields.POSITION}__gte": position}).update(
            position=F(Fields.POSITION) + 1
        )

    def update_positions_to_fill_deleted_ones(self, playlist: Any) -> None:
        tracks_positions_ordered_asc = (
            self.filter(user=playlist.user, playlist=playlist)
            .exclude(**{f"{Fields.POSITION}__isnull": True})
            .order_by(Fields.POSITION)
        )

        for i, relation in enumerate(tracks_positions_ordered_asc, 1):
            relation.position = i
            relation.save(update_fields=[Fields.POSITION])

    def delete_instance(self, user: Any, playlist: Any, track: Any) -> None:
        track_playlist_rel: T = self.get(user=user, playlist=playlist, track=track)
        if track_playlist_rel.position is not None:
            self._decrement_positions_of_following_tracks(playlist, track_playlist_rel.position)
        track_playlist_rel.delete()

    def move_tracks_to_playlist_beginning(self, source_rels: QuerySet[T], target_playlist: Any) -> None:
        if not source_rels:
            return

        self.filter(user=target_playlist.user, playlist=target_playlist, position__isnull=False).update(
            position=F(Fields.POSITION) + source_rels.count()
        )

        for i, relation in enumerate(source_rels.order_by(Fields.POSITION), 1):
            relation.playlist = target_playlist
            relation.position = i
            relation.save(update_fields=[Fields.POSITION, Fields.PLAYLIST])

    def get_ordered_relations_for_playlist(self, playlist: Any) -> QuerySet[T]:
        """
        Returns ordered relations for a playlist, positioned tracks first (sorted by position)
        followed by unpositioned ones (null positions).
        """
        return (
            self.filter(user=playlist.user, playlist=playlist)
            .select_related(Fields.TRACK_INTERNAL)
            .order_by(F(Fields.POSITION).desc(nulls_last=True), Fields.POSITION)
        )
