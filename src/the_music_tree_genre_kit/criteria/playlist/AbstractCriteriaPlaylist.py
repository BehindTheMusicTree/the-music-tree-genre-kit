from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from the_music_tree_api_kit.base.save_context import SaveContext
from the_music_tree_api_kit.field.foreign_key.AppForeignKey import AppForeignKey
from the_music_tree_api_kit.field.foreign_key.PrivateForeignKey import PrivateForeignKey
from the_music_tree_api_kit.field.foreign_key.PrivateOneToOneField import PrivateOneToOneField

from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks

from .CriterialessPlaylistNames import CriterialessPlaylistNames
from .Fields import Fields

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

    parent: AbstractCriteriaPlaylist | None = PrivateForeignKey(
        "self", on_delete=models.SET_NULL, null=True, related_name=Fields.CHILDREN
    )  # type: ignore

    root: AbstractCriteriaPlaylist = PrivateForeignKey(
        "self", on_delete=models.DO_NOTHING, related_name=Fields.ROOT_DESCENDANTS
    )  # type: ignore

    type = AppForeignKey(CriteriaType, on_delete=models.CASCADE)

    class Meta:
        abstract = True

    if TYPE_CHECKING:
        children: QuerySet[AbstractCriteriaPlaylist]

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

    @property
    def is_root(self) -> bool:
        return self.root == self

    def __str__(self) -> str:
        parent_str = f"Parent: {self.parent.name}" if self.parent else "Parent: None"
        root_str = f"Root: {self.root.name}" if self.root else "Root: None"
        return f"{self.uuid} | {self.name} | {parent_str} | {root_str}"

    def _set_parent(self) -> bool:
        current_parent_pk = getattr(self, f"{Fields.PARENT}_id", None)

        if self.criteria and self.criteria.parent:
            parent: Any = type(self).objects.get(criteria=self.criteria.parent)
            if current_parent_pk != parent.pk:
                self.parent = parent
                return True
        elif current_parent_pk is not None:
            self.parent = None
            return True
        return False

    def _set_root(self) -> bool:
        current_root_id = getattr(self, f"{Fields.ROOT}_id", None)
        new_root_id = self.pk if not self.criteria or self.criteria.is_root else self.criteria.root.criteria_playlist.pk

        if current_root_id != new_root_id:
            self.root_id = new_root_id
            return True
        return False

    def _prepare_save(self, ctx: SaveContext) -> dict:
        self._set_uuid_if_necessary()
        return ctx.kwargs

    def _perform_save(self, adding: bool, ctx: SaveContext) -> None:
        parent_has_changed = self._set_parent()
        if not adding and parent_has_changed:
            ctx.add_modified_field(Fields.PARENT)

        root_has_changed = self._set_root()
        if not adding and root_has_changed:
            ctx.add_modified_field(f"{Fields.ROOT}_id")

        super()._perform_save(adding=adding, ctx=ctx)

    def _post_save(self, adding: bool) -> None:
        if adding:
            self.root_id = self.pk
            super().save(update_fields=[f"{Fields.ROOT}_id"])
