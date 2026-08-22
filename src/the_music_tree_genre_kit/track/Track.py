from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from the_music_tree_api_kit.field.AppCharField import AppCharField
from the_music_tree_api_kit.field.foreign_key.PrivateForeignKey import PrivateForeignKey
from the_music_tree_api_kit.field.foreign_key.PrivateManyToManyField import PrivateManyToManyField
from the_music_tree_api_kit.trackable_play_count.TrackablePlayCount import TrackablePlayCount

from the_music_tree_genre_kit.playlist.Fields import Fields as PlaylistFields

from .Fields import Fields
from .TrackManager import TrackManager


class Track(TrackablePlayCount):
    """
    Shared parent table for every app's concrete track model, joined via
    Django multi-table inheritance:

        class UploadedTrack(Track):
            track = PrivateOneToOneField(Track, on_delete=models.CASCADE, parent_link=True, ...)
            objects: UploadedTrackManager = UploadedTrackManager()

    Consuming apps must set `settings.ARTIST_MODEL`, `settings.ALBUM_MODEL`
    (in addition to `settings.CRITERIA_MODEL`/`settings.TRACK_MODEL`),
    resolved the same way Django resolves `settings.AUTH_USER_MODEL`.
    """

    title = AppCharField(max_length=settings.TRACK_TITLE_LEN_MAX)
    artists = PrivateManyToManyField(
        settings.ARTIST_MODEL, blank=True, related_name=Fields.TRACKS_OF_ARTIST_RELATED_NAME
    )
    album = PrivateForeignKey(
        settings.ALBUM_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name=Fields.TRACKS_OF_ALBUM_RELATED_NAME,
    )
    track_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(settings.TRACK_TRACK_NUMBER_MAX)],
    )
    genre = PrivateForeignKey(
        settings.CRITERIA_MODEL,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name=Fields.TRACKS_OF_CRITERIA_RELATED_NAME,
    )
    rating = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(settings.TRACK_RATING_VALUE_MAX)],
    )
    language = AppCharField(max_length=settings.LANGUAGE_LEN_MAX, blank=True, default=None, null=True)
    archived = models.BooleanField(default=False)
    playlists = PrivateManyToManyField(
        "the_music_tree_genre_kit.Playlist",
        through="the_music_tree_genre_kit.TrackPlaylistRel",
        related_name=PlaylistFields.TRACKS_RELATED_NAME,
    )

    objects: TrackManager = TrackManager()

    class Meta:
        app_label = "the_music_tree_genre_kit"
        indexes = [
            models.Index(fields=["user", Fields.TITLE]),
            models.Index(fields=["user", Fields.GENRE]),
            models.Index(fields=["user", Fields.ALBUM]),
        ]

    def __str__(self) -> str:
        return f"{self.uuid} | {self.title}"
