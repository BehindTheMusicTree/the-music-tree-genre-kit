from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from the_music_tree_api_kit.base.save_context import SaveContext
from the_music_tree_api_kit.field.foreign_key.AppForeignKey import AppForeignKey
from the_music_tree_api_kit.field.foreign_key.PrivateOneToOneField import PrivateOneToOneField

from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks

from .CriterialessPlaylistNames import CriterialessPlaylistNames

if TYPE_CHECKING:
    from django.db.models import QuerySet


class AbstractCriteriaPlaylist(models.Model):
    """
    Pure abstract mixin owning the criteria/tree fields and behavior shared by
    every app's concrete CriteriaPlaylist. Deliberately does NOT extend any
    Playlist base: each app owns its own concrete, real-MTI Playlist model,
    and the concrete subclass composes both via multiple inheritance:

        class CriteriaPlaylist(AbstractCriteriaPlaylist, Playlist):
            playlist = PrivateOneToOneField(Playlist, on_delete=models.CASCADE, parent_link=True, ...)
            objects: CriteriaPlaylistManager = CriteriaPlaylistManager()

    Consuming apps must set `settings.CRITERIA_MODEL` (e.g. "grow.Criteria"),
    resolved the same way Django resolves `settings.AUTH_USER_MODEL`.
    """

    criteria = PrivateOneToOneField(
        settings.CRITERIA_MODEL,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="criteria_playlist",
    )

    type = AppForeignKey(CriteriaType, on_delete=models.CASCADE)

    class Meta:
        abstract = True

    @property
    def type_label(self) -> str:
        return self.type.label

    @property
    def name_when_no_criteria(self) -> str:
        if self.type.pk == int(CriteriaTypePks.GENRE):
            return CriterialessPlaylistNames.GENRE
        if self.type.pk == int(CriteriaTypePks.TAG):
            return CriterialessPlaylistNames.TAG
        raise ImproperlyConfigured(f"Unknown criteria type: {self.type.pk}")

    @property
    def name(self):
        return self.criteria.name if self.criteria else self.name_when_no_criteria

    # Derived from the criteria tree rather than stored, so the two trees can't drift apart.
    @property
    def parent(self) -> AbstractCriteriaPlaylist | None:
        if self.criteria is None or self.criteria.parent_id is None:
            return None
        return self.criteria.parent.criteria_playlist

    @property
    def root(self) -> AbstractCriteriaPlaylist:
        if self.is_root:
            return self
        return self.criteria.root.criteria_playlist

    @property
    def is_root(self) -> bool:
        return self.criteria is None or self.criteria.parent_id is None

    @property
    def children(self) -> QuerySet[AbstractCriteriaPlaylist]:
        if self.criteria is None:
            return type(self).objects.none()
        return type(self).objects.filter(criteria__parent=self.criteria)

    def __str__(self) -> str:
        parent_str = f"Parent: {self.parent.name}" if self.parent else "Parent: None"
        root_str = f"Root: {self.root.name}" if self.root else "Root: None"
        return f"{self.uuid} | {self.name} | {parent_str} | {root_str}"

    def _prepare_save(self, ctx: SaveContext) -> dict:
        self._set_uuid_if_necessary()
        return ctx.kwargs
