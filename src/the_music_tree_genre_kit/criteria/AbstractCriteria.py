from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import IntegrityError, models
from django.db.models import QuerySet
from django.utils.translation import gettext as _
from the_music_tree_api_kit.base.save_context import SaveContext
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException
from the_music_tree_api_kit.exception.validation.FieldValidationErrorCode import FieldValidationErrorCode
from the_music_tree_api_kit.field.AppCharField import AppCharField
from the_music_tree_api_kit.field.foreign_key.AppForeignKey import AppForeignKey
from the_music_tree_api_kit.field.foreign_key.PrivateForeignKey import PrivateForeignKey
from the_music_tree_api_kit.field.foreign_key.PrivateManyToManyField import PrivateManyToManyField
from the_music_tree_api_kit.private_unique_resource.PrivateUniqueResource import PrivateUniqueResource

from .CriteriaSide import CriteriaSide
from .Fields import Fields
from .lineage_rel.Fields import Fields as CriteriaLineageRelFields
from .type.CriteriaType import CriteriaType
from .type.CriteriaTypePks import CriteriaTypePks

if TYPE_CHECKING:
    from .lineage_rel.AbstractCriteriaLineageRel import AbstractCriteriaLineageRel


class AbstractCriteria(PrivateUniqueResource):
    """
    Owns the pure tree-structure fields and behavior for criteria (name,
    parent/root/ascendants, tree constraints/indexes). Non-tree concerns
    (uploaded tracks, playlists, etc.) are layered in by concrete subclasses.

    Concrete subclasses must also provide a concrete lineage-rel model (a
    subclass of AbstractCriteriaLineageRel named "CriteriaLineageRel" in the
    same app) since `ascendants` below resolves its `through` model by name.
    """

    _name = AppCharField(max_length=settings.CRITERIA_NAME_LEN_MAX, db_column=Fields.NAME_PUBLIC)
    ascendants: QuerySet[AbstractCriteria] = PrivateManyToManyField(
        "self",
        through="CriteriaLineageRel",
        through_fields=(CriteriaLineageRelFields.DESCENDANT, CriteriaLineageRelFields.ASCENDANT),
        symmetrical=False,
    )  # type: ignore
    parent: AbstractCriteria | None = PrivateForeignKey(
        "self", on_delete=models.SET_NULL, null=True, related_name=Fields.CHILDREN
    )  # type: ignore

    root: AbstractCriteria = PrivateForeignKey("self", on_delete=models.DO_NOTHING, related_name=Fields.DESCENDANTS)  # type: ignore

    type = AppForeignKey(CriteriaType, on_delete=models.CASCADE)

    side = AppCharField(max_length=4, choices=CriteriaSide.choices, null=True, blank=True, db_column=Fields.SIDE)
    """
    Meaningful only for a genre criteria that is a root criteria's direct child
    (`parent_id == root_id`); ignored elsewhere, same convention as `is_root` below.
    Null/unset means "core" (the required, non-pop branch); `CriteriaSide.POP` marks
    the optional pop/crossover branch. Only valid on genre-type criteria (see
    `CriteriaTypePks.GENRE`); setting it on any other criteria type raises on save.
    See `_validate_side` for the type, placement, and uniqueness constraints enforced
    on save.
    """

    class Meta:
        abstract = True

    if TYPE_CHECKING:
        ascendants_rels: QuerySet[AbstractCriteriaLineageRel]
        descendants: QuerySet[AbstractCriteria]
        descendants_rels: QuerySet[AbstractCriteriaLineageRel]
        children: QuerySet[AbstractCriteria]

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_root(self) -> bool:
        return not self.parent

    @property
    def descendant_list(self) -> list[AbstractCriteria]:
        """
        Get all descendants of this criteria using the lineage system.
        This is more efficient than recursive traversal as it uses the pre-computed relationships.

        Returns:
            A list of all descendant criteria
        """
        return list(self.descendants.all())

    def __str__(self) -> str:
        parent_str = f"{Fields.PARENT}: {self.parent.name}" if self.parent else f"[no {Fields.PARENT}]"
        created_on_str = f"{Fields.CREATED_ON}: {self.created_on}"
        updated_on_str = f"{Fields.UPDATED_ON}: {self.updated_on}"

        return f"{self.uuid} | {self.name} | {parent_str} | {created_on_str} | {updated_on_str}"

    def _set_root(self):
        current_root = getattr(self, f"{Fields.ROOT}", None)
        new_root = self.parent.root if self.parent else self

        new_root_pk = None
        if not new_root:
            new_root_pk = self.pk
        elif current_root != new_root:
            new_root_pk = new_root.pk

        if new_root_pk:
            self.root_id = new_root_pk
            return True
        return False

    def _validate_side(self) -> None:
        if self.side is not None and self.type_id != int(CriteriaTypePks.GENRE):
            raise AppValidationException(
                field_name=Fields.SIDE,
                message=_("side is only valid on genre criteria"),
                field_validation_error_code=FieldValidationErrorCode.DEPENDENCY_MISSING,
            )

        if self.side != CriteriaSide.POP:
            return

        is_root_direct_child = bool(self.parent_id) and self.parent_id == self.root_id
        if not is_root_direct_child:
            raise AppValidationException(
                field_name=Fields.SIDE,
                message=_('side="pop" is only valid on a direct child of a root criteria'),
                field_validation_error_code=FieldValidationErrorCode.REFERENCE_INVALID,
            )

        duplicate_pop_sibling_exists = (
            type(self)
            .objects.filter(root_id=self.root_id, parent_id=self.parent_id, side=CriteriaSide.POP)
            .exclude(pk=self.pk)
            .exists()
        )
        if duplicate_pop_sibling_exists:
            raise AppValidationException(
                field_name=Fields.SIDE,
                message=_('Only one direct child of a root criteria may have side="pop"'),
                field_validation_error_code=FieldValidationErrorCode.DUPLICATE,
            )

    def _prepare_save(self, ctx: SaveContext) -> dict:
        self._set_uuid_if_necessary()
        root_has_changed = self._set_root()
        if not self._state.adding and root_has_changed:
            ctx.add_modified_field(f"{Fields.ROOT}_id")
        self._validate_side()
        return ctx.kwargs

    def save(self, *args: Any, **kwargs: Any) -> None:
        try:
            super().save(*args, **kwargs)
        except IntegrityError as e:
            error_message = str(e)
            if "non_empty_name" in error_message:
                raise AppValidationException(
                    field_name=Fields.NAME_PUBLIC,
                    message=_("Name cannot be empty"),
                    field_validation_error_code=FieldValidationErrorCode.NAME_EMPTY,
                )
            if "unique_name_per_user" in error_message:
                raise AppValidationException(
                    field_name=Fields.NAME_PUBLIC,
                    message=_(f'The name "{self.name}" is already used'),
                    field_validation_error_code=FieldValidationErrorCode.NAME_DUPLICATE,
                )
            # Let other database integrity errors propagate to be handled as system errors
            raise

    def is_descendant_of(self, other_criteria: AbstractCriteria) -> bool:
        if self.parent == other_criteria:
            return True
        if self.parent:
            return self.parent.is_descendant_of(other_criteria)
        return False
