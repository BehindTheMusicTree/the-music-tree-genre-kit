from typing import TYPE_CHECKING, Any, TypeVar

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

    def _genre_playlists(self, instance: T, genre) -> dict[Any, Any]:
        """The playlists a track with `genre` belongs to: the genre's and every primary ascendant's, or the genreless one."""
        from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks

        if genre is None:
            genreless_playlist = type(self).criteria_playlist_model.objects.get(
                user=instance.user, type=CriteriaTypePks.GENRE, criteria=None
            )
            return {genreless_playlist.pk: genreless_playlist}
        genres = [genre, *(ascendant for ascendant, _degree in genre.primary_ascendants().values())]
        return {item.criteria_playlist.pk: item.criteria_playlist for item in genres}

    def _add_to_genre_playlists(self, instance: T):
        for playlist in self._genre_playlists(instance, instance.genre).values():
            TrackPlaylistRel.objects.create(user=instance.user, playlist=playlist, track=instance)

    def _decrease_position_of_next_tracks_in_old_track_playlists(self, user: User, playlists_with_old_position: list):
        for playlist_uuid, old_position in playlists_with_old_position:
            track_playlist_rels_to_update = TrackPlaylistRel.objects.filter(
                user=user, playlist=playlist_uuid, position__gt=old_position
            )
            track_playlist_rels_to_update.update(position=F("position") - 1)

    def _update_genre_playlists(self, instance: T, old_genre):
        old_playlists = self._genre_playlists(instance, old_genre)
        new_playlists = self._genre_playlists(instance, instance.genre)

        for playlist_pk in new_playlists.keys() - old_playlists.keys():
            TrackPlaylistRel.objects.create(user=instance.user, playlist=new_playlists[playlist_pk], track=instance)
        for playlist_pk in old_playlists.keys() - new_playlists.keys():
            # Genreless tracks from before 0.29 may lack their genreless-playlist rel.
            if (
                old_genre is None
                and not TrackPlaylistRel.objects.filter(
                    user=instance.user, playlist_id=playlist_pk, track=instance
                ).exists()
            ):
                continue
            TrackPlaylistRel.objects.delete_instance(
                user=instance.user, playlist=old_playlists[playlist_pk], track=instance
            )

    def _model_has_field(self, name: str) -> bool:
        return any(field.name == name for field in self.model._meta.get_fields())

    def _model_has_manual_edit_field(self) -> bool:
        """
        Whether this manager's model declares the `is_manually_edited` column. Only a
        concrete video-linkable `Track` subtype (e.g. `YoutubeTrack`) does.
        """
        return self._model_has_field("is_manually_edited")

    def _on_track_genre_changed(self, instance: T, *, old_genre, actor: Any = None) -> None:
        """
        Hook: called whenever `instance.genre` changes via `update_instance` -- distinct from
        `AbstractCriteriaManager._on_track_genre_cleared`, which only fires when the
        track's genre criteria itself gets deleted. No-op by default; a concrete app
        overrides it to log history.
        """

    def create(self, actor: Any = None, **kwargs) -> T:
        with transaction.atomic():
            artists = kwargs.pop(Fields.ARTISTS, None)

            instance: T = super().create(**kwargs)
            if artists:
                instance.artists.set(artists)

            self._add_to_genre_playlists(instance)

        return instance

    def update_instance(self, old_instance: T, actor: Any = None, **kwargs) -> T:
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

            updated_instance: T = super().update_instance(old_instance, **kwargs)

            if old_genre != updated_instance.genre:
                self._update_genre_playlists(updated_instance, old_genre=old_genre)
                self._on_track_genre_changed(updated_instance, old_genre=old_genre, actor=actor)

            if old_album and updated_instance.album and old_album != updated_instance.album:
                album_model.objects.delete_instance_if_no_track_linked_with_potential_album_artist_deletion(old_album)
                for album_artist in old_album_artists_list:
                    artist_model.objects.delete_instance_if_nothing_linked(album_artist)

            if len(old_artists_list) > 0:
                current_track_artists_list = list(updated_instance.artists.all())
                for old_track_artist in old_artists_list:
                    if old_track_artist not in current_track_artists_list:
                        artist_model.objects.delete_instance_if_nothing_linked(old_track_artist)

            self._on_updated(old_instance, updated_instance)

            return updated_instance

    def _on_updated(self, old_instance: T, updated_instance: T) -> None:
        """Hook for consumers to react to a track update, inside its transaction."""

    def delete_instance(self, instance: T, actor: Any = None):
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
