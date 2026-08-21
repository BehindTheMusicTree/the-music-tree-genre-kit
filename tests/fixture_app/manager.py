from django.db import models
from the_music_tree_api_kit.public_standard_resource.StandardResourceManager import StandardResourceManager

from the_music_tree_genre_kit.criteria.AbstractCriteriaManager import AbstractCriteriaManager
from the_music_tree_genre_kit.criteria.playlist.AbstractCriteriaPlaylistManager import AbstractCriteriaPlaylistManager
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType


class CriteriaManager(AbstractCriteriaManager):
    def _get_criteria_type(self) -> CriteriaType:
        return CriteriaType.objects.get_or_create(label="fixture-criteria-type")[0]


class PlaylistManager(StandardResourceManager):
    pass


class TrackManager(StandardResourceManager):
    pass


class TrackPlaylistRelManager(StandardResourceManager):
    def update_positions_to_fill_deleted_ones(self, playlist) -> None:
        rels = self.filter(playlist=playlist, position__isnull=False).order_by("position")
        for position, rel in enumerate(rels, start=1):
            if rel.position != position:
                rel.position = position
                rel.save(update_fields=["position"])

    def move_tracks_to_playlist_beginning(self, *, source_rels, target_playlist) -> None:
        source_rels = list(source_rels.order_by("position"))
        if not source_rels:
            return

        self.filter(playlist=target_playlist, position__isnull=False).update(
            position=models.F("position") + len(source_rels)
        )

        for position, rel in enumerate(source_rels, start=1):
            rel.playlist = target_playlist
            rel.position = position
            rel.save(update_fields=["playlist", "position"])


class CriteriaPlaylistManager(AbstractCriteriaPlaylistManager):
    def _get_direct_tracks(self, instance):
        from tests.fixture_app.models import Track

        return Track.objects.filter(track_playlist_rels__playlist=instance)

    def _create_track_rel(self, *, user, playlist, track) -> None:
        from tests.fixture_app.models import TrackPlaylistRel

        TrackPlaylistRel.objects.create(user=user, playlist=playlist, track=track)

    def _delete_track_rels_and_fill_positions(self, *, instance, tracks) -> None:
        from tests.fixture_app.models import TrackPlaylistRel

        instance.track_playlist_rels.filter(track__in=tracks).delete()
        TrackPlaylistRel.objects.update_positions_to_fill_deleted_ones(instance)

    def _get_track_rels_for_tracks(self, *, playlist, tracks):
        return playlist.track_playlist_rels.filter(track__in=tracks)

    def _move_track_rels_to_playlist_beginning(self, *, source_rels, target_playlist) -> None:
        from tests.fixture_app.models import TrackPlaylistRel

        TrackPlaylistRel.objects.move_tracks_to_playlist_beginning(
            source_rels=source_rels, target_playlist=target_playlist
        )
