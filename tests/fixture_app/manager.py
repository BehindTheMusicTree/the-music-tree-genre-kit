from the_music_tree_api_kit.public_standard_resource.StandardResourceManager import StandardResourceManager

from the_music_tree_genre_kit.criteria.AbstractCriteriaManager import AbstractCriteriaManager
from the_music_tree_genre_kit.criteria.playlist.AbstractCriteriaPlaylistManager import AbstractCriteriaPlaylistManager
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks
from the_music_tree_genre_kit.track.AbstractTrackManager import AbstractTrackManager


class CriteriaManager(AbstractCriteriaManager):
    def _get_criteria_type(self) -> CriteriaType:
        return CriteriaType.objects.get_or_create(
            pk=int(CriteriaTypePks.GENRE), defaults={"label": "fixture-criteria-type"}
        )[0]


class ArtistManager(StandardResourceManager):
    def delete_instance_if_nothing_linked(self, instance):
        if instance.albums.count() == 0 and instance.tracks_of_artist.count() == 0:
            return instance.delete()
        return 0, {}

    def get_artists_list_from_names_after_potential_creation(self, user, artists_names):
        return [self.get_or_create(user=user, name=name)[0] for name in (artists_names or [])]


class AlbumManager(StandardResourceManager):
    def delete_instance_if_no_track_linked_with_potential_album_artist_deletion(self, instance):
        if instance.tracks_of_album.count() == 0:
            album_artists = list(instance.album_artists.all())
            instance.delete()
            for album_artist in album_artists:
                ArtistManager().delete_instance_if_nothing_linked(album_artist)


class TrackManager(AbstractTrackManager):
    pass


class CriteriaPlaylistManager(AbstractCriteriaPlaylistManager):
    pass
