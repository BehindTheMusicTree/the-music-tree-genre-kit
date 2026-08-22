from typing import TYPE_CHECKING, TypeVar

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import F
from the_music_tree_api_kit.public_standard_resource.StandardResourceManager import StandardResourceManager

from the_music_tree_genre_kit.criteria.track_playlist_rel.TrackPlaylistRel import TrackPlaylistRel

from .Fields import Fields

if TYPE_CHECKING:
    from .Track import Track

T = TypeVar("T", bound="Track")


class AbstractTrackManager(StandardResourceManager[T]):
    """
    Fully concrete except for `criteria_playlist_model`, a plain class
    attribute wired by the concrete app's manager module (mirroring
    `AbstractCriteriaManager.lineage_rel_model`), since the criteria-less
    playlist bootstrap needs the app's concrete `CriteriaPlaylist` model,
    which has no dedicated swappable-model setting:

        class TrackManager(AbstractTrackManager):
            pass

        TrackManager.criteria_playlist_model = CriteriaPlaylist
    """

    model: type[T]
    criteria_playlist_model: type[models.Model]

    def _remove_from_genre_playlists(self, instance: T, old_genre, genre_limit=None):
        from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks

        criteria_playlist_model = type(self).criteria_playlist_model

        if old_genre:
            old_genre_tree_item = old_genre
            while old_genre_tree_item != genre_limit:
                TrackPlaylistRel.objects.delete_instance(
                    user=instance.user, playlist=old_genre_tree_item.criteria_playlist, track=instance
                )

                # The loop will stop before genre_tree_item is None
                old_genre_tree_item = old_genre_tree_item.parent

        else:
            genreless_criteria_playlist = criteria_playlist_model.objects.get(
                user=instance.user, type=CriteriaTypePks.GENRE, criteria=None
            )
            TrackPlaylistRel.objects.filter(playlist=genreless_criteria_playlist, track=instance).delete()

    def _add_to_genre_playlists(self, instance: T, genre_limit=None):
        from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks

        criteria_playlist_model = type(self).criteria_playlist_model

        if instance.genre:
            genre_tree_item = instance.genre
            while genre_tree_item != genre_limit:
                TrackPlaylistRel.objects.create(
                    user=instance.user, playlist=genre_tree_item.criteria_playlist, track=instance
                )

                # The loop will stop before genre_tree_item is None
                genre_tree_item = genre_tree_item.parent
        else:
            genreless_criteria_playlist = criteria_playlist_model.objects.get(
                user=instance.user, type=CriteriaTypePks.GENRE, criteria=None
            )
            TrackPlaylistRel.objects.create(user=instance.user, playlist=genreless_criteria_playlist, track=instance)

    def _decrease_position_of_next_tracks_in_old_track_playlists(self, user: User, playlists_with_old_position: list):
        for playlist_uuid, old_position in playlists_with_old_position:
            track_playlist_rels_to_update = TrackPlaylistRel.objects.filter(
                user=user, playlist=playlist_uuid, position__gt=old_position
            )
            track_playlist_rels_to_update.update(position=F("position") - 1)

    def _update_genre_playlists(self, instance: T, old_genre):
        criteria_model = apps.get_model(settings.CRITERIA_MODEL)

        common_genre = (
            criteria_model.objects.get_common_ascendant(instance.genre, old_genre)
            if old_genre and instance.genre
            else None
        )

        self._add_to_genre_playlists(instance=instance, genre_limit=common_genre)
        self._remove_from_genre_playlists(instance=instance, old_genre=old_genre, genre_limit=common_genre)

    def create(self, **kwargs) -> T:
        with transaction.atomic():
            artists = kwargs.pop(Fields.ARTISTS, None)

            instance: T = super().create(**kwargs)
            if artists:
                instance.artists.set(artists)

            self._add_to_genre_playlists(instance)

        return instance

    def update_instance(self, old_instance: T, **kwargs) -> T:
        album_model = apps.get_model(settings.ALBUM_MODEL)
        artist_model = apps.get_model(settings.ARTIST_MODEL)

        with transaction.atomic():
            old_album_artists_list = []
            if old_instance.album:
                # list() makes a copy of the QuerySet before the deletion
                old_album_artists_list = list(old_instance.album.album_artists.all())
                old_album = old_instance.album
            else:
                old_album = None

            old_genre = old_instance.genre
            # list() makes a copy of the QuerySet before the deletion
            old_artists_list = list(old_instance.artists.all())

            old_archived_state = old_instance.archived

            updated_instance: T = super().update_instance(old_instance, **kwargs)

            if old_genre != updated_instance.genre:
                self._update_genre_playlists(updated_instance, old_genre=old_genre)

            if old_album and updated_instance.album and old_album != updated_instance.album:
                album_model.objects.delete_instance_if_no_track_linked_with_potential_album_artist_deletion(old_album)
                for album_artist in old_album_artists_list:
                    artist_model.objects.delete_instance_if_nothing_linked(album_artist)

            if len(old_artists_list) > 0:
                current_track_artists_list = list(updated_instance.artists.all())
                for old_track_artist in old_artists_list:
                    if old_track_artist not in current_track_artists_list:
                        artist_model.objects.delete_instance_if_nothing_linked(old_track_artist)

            if old_archived_state != updated_instance.archived:
                if updated_instance.archived:
                    TrackPlaylistRel.objects.archive_instances_of_track(track=updated_instance)
                else:
                    TrackPlaylistRel.objects.unarchive_instances_of_track(track=updated_instance)

            return updated_instance

    def delete_instance(self, instance: T):
        with transaction.atomic():
            old_playlists_with_positions = instance.playlists_with_positions
            user = instance.user
            self.delete_instance_with_checking_album_and_artists_potential_deletion(instance)
            self._decrease_position_of_next_tracks_in_old_track_playlists(
                user=user, playlists_with_old_position=old_playlists_with_positions
            )

    def delete_instance_with_checking_album_and_artists_potential_deletion(self, instance: T):
        album_model = apps.get_model(settings.ALBUM_MODEL)
        artist_model = apps.get_model(settings.ARTIST_MODEL)

        artists = list(instance.artists.all())  # list() makes a copy of the QuerySet before the deletion
        album = instance.album

        # The order of the deletions is important for deletion rollback testing. Be carefull before changing it.
        instance.delete()

        if album:
            album_model.objects.delete_instance_if_no_track_linked_with_potential_album_artist_deletion(album)
        for artist in artists:
            artist_model.objects.delete_instance_if_nothing_linked(artist)
