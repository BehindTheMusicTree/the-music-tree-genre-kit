from typing import TYPE_CHECKING

from django.db import models
from the_music_tree_api_kit.field.foreign_key.PrivateOneToOneField import PrivateOneToOneField
from the_music_tree_api_kit.private_unique_resource.PrivateUniqueResource import PrivateUniqueResource

from tests.fixture_app.manager import (
    CriteriaManager,
    CriteriaPlaylistManager,
    PlaylistManager,
    TrackManager,
    TrackPlaylistRelManager,
)
from the_music_tree_genre_kit.criteria.AbstractCriteria import AbstractCriteria
from the_music_tree_genre_kit.criteria.Fields import Fields as CriteriaFields
from the_music_tree_genre_kit.criteria.lineage_rel.AbstractCriteriaLineageRel import AbstractCriteriaLineageRel
from the_music_tree_genre_kit.criteria.playlist.AbstractCriteriaPlaylist import AbstractCriteriaPlaylist
from the_music_tree_genre_kit.criteria.track_playlist_rel.AbstractTrackPlaylistRel import AbstractTrackPlaylistRel


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


class Playlist(PrivateUniqueResource):
    objects: PlaylistManager = PlaylistManager()

    if TYPE_CHECKING:
        track_playlist_rels: models.QuerySet[TrackPlaylistRel]
        criteria_playlist: CriteriaPlaylist | None

    class Meta:
        app_label = "fixture_app"


class Track(PrivateUniqueResource):
    title = models.CharField(max_length=255, blank=True, default="")

    objects: TrackManager = TrackManager()

    class Meta:
        app_label = "fixture_app"


class CriteriaPlaylist(AbstractCriteriaPlaylist, Playlist):  # type: ignore[django-manager-missing]
    playlist = PrivateOneToOneField(
        Playlist, on_delete=models.CASCADE, parent_link=True, related_name="criteria_playlist"
    )

    objects: CriteriaPlaylistManager = CriteriaPlaylistManager()

    class Meta:
        app_label = "fixture_app"


class TrackPlaylistRel(AbstractTrackPlaylistRel):
    objects: TrackPlaylistRelManager = TrackPlaylistRelManager()

    class Meta:
        app_label = "fixture_app"


CriteriaPlaylistManager.track_playlist_rel_model = TrackPlaylistRel
CriteriaPlaylistManager.track_model = Track
