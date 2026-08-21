from typing import TYPE_CHECKING, Any, TypeVar

from django.db import models
from django.db.models import QuerySet
from the_music_tree_api_kit.public_standard_resource.StandardResourceManager import StandardResourceManager

from .AbstractCriteriaPlaylist import AbstractCriteriaPlaylist
from .CriterialessPlaylistNames import CriterialessPlaylistNames
from .Fields import Fields

if TYPE_CHECKING:
    from the_music_tree_genre_kit.criteria.AbstractCriteria import AbstractCriteria

T = TypeVar("T", bound=AbstractCriteriaPlaylist)


class AbstractCriteriaPlaylistManager(StandardResourceManager[T]):
    """
    Owns the pure tree-structure logic for criteria playlists (root
    propagation) plus the track-touching logic that used to be duplicated
    line-for-line between grow and hear. Since the two apps' track models
    diverge (Track/TrackPlaylistRel vs UploadedTrack/UploadedTrackPlaylistRel),
    the track-touching methods are generic bodies built on required-override
    hooks below — there is no sensible generic default for "what is a track
    rel here", so these hooks raise NotImplementedError rather than being
    no-ops, mirroring AbstractCriteriaManager's `_get_criteria_type` style.
    """

    def _get_direct_tracks(self, instance: T) -> QuerySet:
        """Hook: return the queryset of tracks directly on this playlist. Must be overridden."""
        raise NotImplementedError

    def _create_track_rel(self, *, user: Any, playlist: T, track: Any) -> None:
        """Hook: create and save a track-playlist rel for `track` on `playlist`. Must be overridden."""
        raise NotImplementedError

    def _delete_track_rels_and_fill_positions(self, *, instance: T, tracks: QuerySet) -> None:
        """Hook: delete `instance`'s rels for `tracks` and fill the resulting position gaps. Must be overridden."""
        raise NotImplementedError

    def _get_track_rels_for_tracks(self, *, playlist: T, tracks: QuerySet) -> QuerySet:
        """Hook: return `playlist`'s track-playlist rels for `tracks`. Must be overridden."""
        raise NotImplementedError

    def _move_track_rels_to_playlist_beginning(self, *, source_rels: QuerySet, target_playlist: T) -> None:
        """Hook: move `source_rels` to the beginning of `target_playlist`. Must be overridden."""
        raise NotImplementedError

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

    def update_instance(self, instance: T, **kwargs) -> T:
        original_root = instance.root
        updated_instance: T = super().update_instance(instance, **kwargs)
        if original_root != updated_instance.root:
            self.update_descendants_root(instance=updated_instance, root=updated_instance.root)
        return updated_instance

    def update_instance_and_children_root(self, instance: T, root: T) -> None:
        instance.root = root
        instance.save(update_fields=[Fields.ROOT])
        self.update_descendants_root(instance=instance, root=root)

    def update_descendants_root(self, instance: T, root: T) -> None:
        for child in instance.children.all():
            self.update_instance_and_children_root(instance=child, root=root)

    def update_ascendants_tracks(
        self, instance: T, old_parent: AbstractCriteria | None, common_criteria: AbstractCriteria | None
    ) -> None:
        if instance.parent:
            self.add_tracks_to_instance_and_ascendants_until_criteria_limit(
                instance=instance.parent, tracks=self._get_direct_tracks(instance), criteria_limit=common_criteria
            )

        if old_parent:
            self.remove_tracks_from_instance_and_ascendants_until_criteria_limit(
                instance=old_parent.criteria_playlist,
                tracks=self._get_direct_tracks(instance),
                criteria_limit=common_criteria,
            )

    def add_tracks_to_instance_and_ascendants_until_criteria_limit(
        self,
        instance: T,
        tracks: QuerySet,
        criteria_limit: AbstractCriteria | None = None,
    ) -> None:
        if instance.criteria != criteria_limit:
            for track in tracks:
                self._create_track_rel(user=instance.user, playlist=instance, track=track)

            if instance.parent:
                self.add_tracks_to_instance_and_ascendants_until_criteria_limit(
                    instance=instance.parent, tracks=tracks, criteria_limit=criteria_limit
                )

    def remove_tracks_from_instance_and_ascendants_until_criteria_limit(
        self,
        instance: T,
        tracks: QuerySet,
        criteria_limit: AbstractCriteria | None = None,
    ) -> None:
        if instance.criteria != criteria_limit:
            self._delete_track_rels_and_fill_positions(instance=instance, tracks=tracks)

            if instance.parent:
                self.remove_tracks_from_instance_and_ascendants_until_criteria_limit(
                    instance=instance.parent, tracks=tracks, criteria_limit=criteria_limit
                )

    def transfer_direct_tracks_to_criterialess_playlist(self, direct_tracks: QuerySet, criteria_playlist: T) -> None:
        criterialess_playlist = self.get(user=criteria_playlist.user, criteria=None, type=criteria_playlist.type)

        direct_tracks_rels_in_criteria_playlist = self._get_track_rels_for_tracks(
            playlist=criteria_playlist, tracks=direct_tracks
        )

        direct_tracks_rels_not_archived = direct_tracks_rels_in_criteria_playlist.filter(position__isnull=False)

        self._move_track_rels_to_playlist_beginning(
            source_rels=direct_tracks_rels_not_archived, target_playlist=criterialess_playlist
        )

        direct_tracks_rels_in_criteria_playlist.filter(position__isnull=True).update(playlist=criterialess_playlist)

    def make_playlist_root(self, playlist: T) -> None:
        playlist.parent = None
        playlist.root = playlist
        playlist.save(update_fields=[Fields.PARENT, Fields.ROOT])

        self.update_descendants_root(instance=playlist, root=playlist)
