from django.conf import settings
from django.db import models
from the_music_tree_api_kit.field.AppCharField import AppCharField

from .Fields import Fields
from .ManualPlaylistTypeLabel import VALUE as MANUAL_PLAYLIST_TYPE_LABEL


class AbstractManualPlaylist(models.Model):
    _name = AppCharField(
        max_length=settings.MANUAL_PLAYLIST_NAME_LEN_MAX, blank=False, null=False, db_column=Fields.NAME_PUBLIC
    )  # type: ignore

    class Meta:
        abstract = True

    @property
    def name(self) -> str:
        return self._name

    @property
    def type_label(self) -> str:
        return MANUAL_PLAYLIST_TYPE_LABEL
