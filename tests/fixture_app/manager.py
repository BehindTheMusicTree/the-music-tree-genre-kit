from the_music_tree_api_kit.public_standard_resource.StandardResourceManager import StandardResourceManager

from the_music_tree_genre_kit.criteria.AbstractCriteriaManager import AbstractCriteriaManager
from the_music_tree_genre_kit.criteria.playlist.AbstractCriteriaPlaylistManager import AbstractCriteriaPlaylistManager
from the_music_tree_genre_kit.criteria.track_playlist_rel.AbstractTrackPlaylistRelManager import (
    AbstractTrackPlaylistRelManager,
)
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType


class CriteriaManager(AbstractCriteriaManager):
    def _get_criteria_type(self) -> CriteriaType:
        return CriteriaType.objects.get_or_create(label="fixture-criteria-type")[0]


class PlaylistManager(StandardResourceManager):
    pass


class TrackManager(StandardResourceManager):
    pass


class CriteriaPlaylistManager(AbstractCriteriaPlaylistManager):
    pass


class TrackPlaylistRelManager(AbstractTrackPlaylistRelManager):
    pass
