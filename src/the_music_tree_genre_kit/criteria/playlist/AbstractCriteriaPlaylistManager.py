import uuid
from typing import TYPE_CHECKING, Any, TypeVar

from django.db import models
from django.db.models import F, QuerySet
from the_music_tree_api_kit.public_standard_resource.StandardResourceManager import StandardResourceManager

from the_music_tree_genre_kit.base.bulk_mti import bulk_create_mti

from .AbstractCriteriaPlaylist import AbstractCriteriaPlaylist
from .CriterialessPlaylistNames import CriterialessPlaylistNames

if TYPE_CHECKING:
    from the_music_tree_genre_kit.criteria.AbstractCriteria import AbstractCriteria

T = TypeVar("T", bound=AbstractCriteriaPlaylist)


class AbstractCriteriaPlaylistManager(StandardResourceManager[T]):
    """
    Owns the track-touching primitives (track rels, criteria-less transfer) that
    used to be duplicated line-for-line between grow and hear. Fully
    concrete: track-touching methods are built on `track_playlist_rel_model`/
    `track_model`, plain class attributes wired by the concrete app's manager
    module, mirroring `AbstractCriteriaManager.lineage_rel_model`:

        class CriteriaPlaylistManager(AbstractCriteriaPlaylistManager):
            pass

        CriteriaPlaylistManager.track_playlist_rel_model = TrackPlaylistRel
        CriteriaPlaylistManager.track_model = Track
    """

    model: type[T]
    track_playlist_rel_model: type[models.Model]
    track_model: type[models.Model]

    def bulk_create_for_criteria(self, criteria_instances: list[AbstractCriteria]) -> None:
        """
        Bulk-creates one playlist per given criteria -- meant to be called
        from a consumer's `_on_bulk_created` override.
        """
        if not criteria_instances:
            return

        playlists: list[T] = []

        for criteria in criteria_instances:
            playlist: T = self.model(user=criteria.user, criteria=criteria, type=criteria.type)

            pk = uuid.uuid4()
            playlist.uuid = pk
            playlist.pk = pk

            playlists.append(playlist)

        bulk_create_mti(playlists, using=self.db)

    def get_direct_tracks(self, instance: T) -> QuerySet:
        track_ids = self.track_playlist_rel_model.objects.filter(playlist=instance).values_list("track_id", flat=True)
        return self.track_model.objects.filter(pk__in=track_ids)

    def _create_track_rel(self, *, user: Any, playlist: T, track: Any) -> None:
        self.track_playlist_rel_model(user=user, playlist=playlist, track=track).save()

    def _bulk_prepend_track_rels(self, *, user: Any, playlist: T, tracks: list[Any]) -> None:
        """
        Set-based equivalent of `_create_track_rel` per track: one shift of the playlist's positioned rels
        plus one insert, instead of a full-playlist renumbering per track.
        """
        rel_model = self.track_playlist_rel_model
        present_ids = set(rel_model.objects.filter(playlist=playlist).values_list("track_id", flat=True))
        missing = [track for track in tracks if track.pk not in present_ids]
        if not missing:
            return
        rel_model.objects.filter(user=user, playlist=playlist, position__isnull=False).update(
            position=F("position") + len(missing)
        )
        rel_model.objects.bulk_create(
            [
                rel_model(user=user, playlist=playlist, track=track, position=position)
                for position, track in enumerate(reversed(missing), 1)
            ]
        )

    def _delete_track_rels_and_fill_positions(self, *, instance: T, tracks: QuerySet) -> None:
        self.track_playlist_rel_model.objects.filter(playlist=instance, track__in=tracks).delete()
        self.track_playlist_rel_model.objects.update_positions_to_fill_deleted_ones(instance)

    def _get_track_rels_for_tracks(self, *, playlist: T, tracks: QuerySet) -> QuerySet:
        return self.track_playlist_rel_model.objects.filter(playlist=playlist, track__in=tracks)

    def _move_track_rels_to_playlist_beginning(self, *, source_rels: QuerySet, target_playlist: T) -> None:
        self.track_playlist_rel_model.objects.move_tracks_to_playlist_beginning(
            source_rels=source_rels, target_playlist=target_playlist
        )

    def get_by_name(self, user: Any, name: str) -> T | None:
        return (
            self.filter(user=user)
            .filter(
                models.Q(criteria__name=name)
                | models.Q(
                    criteria__isnull=True,
                    type__in=[
                        models.Q(name=CriterialessPlaylistNames.GENRE) | models.Q(name=CriterialessPlaylistNames.TAG)
                    ],
                )
            )
            .first()
        )

    def transfer_direct_tracks_to_criterialess_playlist(self, direct_tracks: QuerySet, criteria_playlist: T) -> None:
        criterialess_playlist = self.get(user=criteria_playlist.user, criteria=None, type=criteria_playlist.type)

        direct_tracks_rels_in_criteria_playlist = self._get_track_rels_for_tracks(
            playlist=criteria_playlist, tracks=direct_tracks
        )
        direct_tracks_rels_in_criteria_playlist.filter(
            track__in=self.track_playlist_rel_model.objects.filter(playlist=criterialess_playlist).values("track")
        ).delete()

        direct_positioned_tracks_rels = direct_tracks_rels_in_criteria_playlist.filter(position__isnull=False)

        self._move_track_rels_to_playlist_beginning(
            source_rels=direct_positioned_tracks_rels, target_playlist=criterialess_playlist
        )

        direct_tracks_rels_in_criteria_playlist.filter(position__isnull=True).update(playlist=criterialess_playlist)
