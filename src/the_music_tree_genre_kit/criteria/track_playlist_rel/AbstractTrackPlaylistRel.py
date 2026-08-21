from django.conf import settings
from django.db import models
from django.db.models import Case, F, Value, When
from the_music_tree_api_kit.base.save_context import SaveContext
from the_music_tree_api_kit.field.foreign_key.PrivateForeignKey import PrivateForeignKey
from the_music_tree_api_kit.private_standard_resource.PrivateStandardResource import PrivateStandardResource

from .Fields import Fields


class AbstractTrackPlaylistRel(PrivateStandardResource):
    """
    Owns the `playlist`/`track`/`position` fields and position-shift-on-insert
    behavior shared by every app's concrete track-playlist relation table.

    Consuming apps must set `settings.PLAYLIST_MODEL` (e.g. "grow.Playlist"),
    resolved the same way Django resolves `settings.AUTH_USER_MODEL`. `track`
    points at the kit's own shared `Track` model directly (not
    `settings.TRACK_MODEL`, which names each app's concrete/leaf track type)
    because this model backs `Track.playlists`'s `through=`, and Django
    requires a many-to-many's through model to FK the exact model the field
    is declared on, not one of its multi-table-inheritance subclasses.
    Concrete subclasses set their own `db_table` and indexes.
    """

    playlist = PrivateForeignKey(
        settings.PLAYLIST_MODEL, on_delete=models.CASCADE, related_name=Fields.TRACK_PLAYLIST_RELS_RELATED_NAME
    )
    track = PrivateForeignKey(
        "the_music_tree_genre_kit.Track",
        on_delete=models.CASCADE,
        related_name=Fields.TRACK_PLAYLIST_RELS_RELATED_NAME,
    )
    position = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return (
            f'Playlist "{self.playlist.name}" | Track title "{self.track.title}" | '
            f"Position {self.position} User {self.user}"
        )

    def _perform_save(self, adding: bool, ctx: SaveContext) -> None:
        if adding:
            type(self).objects.filter(user=self.user, playlist=self.playlist).update(
                position=Case(
                    When(**{f"{Fields.POSITION}__isnull": False}, then=F(Fields.POSITION) + 1), default=Value(None)
                )
            )
            self.position = 1
        super()._perform_save(adding, ctx)
