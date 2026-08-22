from typing import TYPE_CHECKING

from django.db import models
from the_music_tree_api_kit.field.foreign_key.PrivateManyToManyField import PrivateManyToManyField
from the_music_tree_api_kit.field.foreign_key.PrivateOneToOneField import PrivateOneToOneField
from the_music_tree_api_kit.private_unique_resource.PrivateUniqueResource import PrivateUniqueResource

from tests.fixture_app.manager import (
    AlbumManager,
    ArtistManager,
    CriteriaManager,
    CriteriaPlaylistManager,
    TrackManager,
    TrackPlaylistRelManager,
)
from the_music_tree_genre_kit.criteria.AbstractCriteria import AbstractCriteria
from the_music_tree_genre_kit.criteria.Fields import Fields as CriteriaFields
from the_music_tree_genre_kit.criteria.lineage_rel.AbstractCriteriaLineageRel import AbstractCriteriaLineageRel
from the_music_tree_genre_kit.criteria.playlist.AbstractCriteriaPlaylist import AbstractCriteriaPlaylist
from the_music_tree_genre_kit.criteria.track_playlist_rel.AbstractTrackPlaylistRel import AbstractTrackPlaylistRel
from the_music_tree_genre_kit.manual_playlist.AbstractManualPlaylist import AbstractManualPlaylist
from the_music_tree_genre_kit.playlist.Fields import Fields as PlaylistFields
from the_music_tree_genre_kit.playlist.Playlist import Playlist as KitPlaylist
from the_music_tree_genre_kit.playlist.PlaylistManager import PlaylistManager as KitPlaylistManager
from the_music_tree_genre_kit.track.Track import Track as KitTrack


class Criteria(AbstractCriteria):
    objects: CriteriaManager = CriteriaManager()

    class Meta:
        app_label = "fixture_app"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(**{f"{CriteriaFields.NAME_INTERNAL}": ""}), name="non_empty_name"
            ),
            models.UniqueConstraint(fields=[CriteriaFields.NAME_INTERNAL, "user"], name="unique_name_per_user"),
        ]


class CriteriaLineageRel(AbstractCriteriaLineageRel):
    descendant = models.ForeignKey(Criteria, on_delete=models.CASCADE, related_name=CriteriaFields.ASCENDANTS_RELS)
    ascendant = models.ForeignKey(Criteria, on_delete=models.CASCADE, related_name=CriteriaFields.DESCENDANTS_RELS)

    class Meta:
        app_label = "fixture_app"


CriteriaManager.lineage_rel_model = CriteriaLineageRel


class Artist(PrivateUniqueResource):
    name = models.CharField(max_length=255, blank=True, default="")

    objects: ArtistManager = ArtistManager()

    if TYPE_CHECKING:
        albums: models.QuerySet[Album]
        tracks_of_artist: models.QuerySet[Track]

    class Meta:
        app_label = "fixture_app"


class Album(PrivateUniqueResource):
    name = models.CharField(max_length=255, blank=True, default="")
    album_artists = PrivateManyToManyField(Artist, blank=True, related_name="albums")

    objects: AlbumManager = AlbumManager()

    if TYPE_CHECKING:
        tracks_of_album: models.QuerySet[Track]

    class Meta:
        app_label = "fixture_app"


class Track(KitTrack):
    track = PrivateOneToOneField(KitTrack, on_delete=models.CASCADE, parent_link=True, related_name="fixture_track")

    objects: TrackManager = TrackManager()

    class Meta:
        app_label = "fixture_app"


class CriteriaPlaylist(AbstractCriteriaPlaylist, KitPlaylist):  # type: ignore[django-manager-missing]
    playlist = PrivateOneToOneField(
        KitPlaylist, on_delete=models.CASCADE, parent_link=True, related_name=PlaylistFields.CRITERIA_PLAYLIST
    )

    objects: CriteriaPlaylistManager = CriteriaPlaylistManager()

    class Meta:
        app_label = "fixture_app"


class ManualPlaylist(AbstractManualPlaylist, KitPlaylist):  # type: ignore[django-manager-missing]
    playlist = PrivateOneToOneField(
        KitPlaylist, on_delete=models.CASCADE, parent_link=True, related_name=PlaylistFields.MANUAL_PLAYLIST
    )

    objects: KitPlaylistManager = KitPlaylistManager()

    class Meta:
        app_label = "fixture_app"


class TrackPlaylistRel(AbstractTrackPlaylistRel):
    objects: TrackPlaylistRelManager = TrackPlaylistRelManager()

    class Meta:
        app_label = "fixture_app"


CriteriaPlaylistManager.track_playlist_rel_model = TrackPlaylistRel
CriteriaPlaylistManager.track_model = Track
TrackManager.criteria_playlist_model = CriteriaPlaylist
