from typing import TYPE_CHECKING, Any

from django.db import models
from django.utils.translation import gettext as _
from the_music_tree_api_kit.base.save_context import SaveContext
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException
from the_music_tree_api_kit.exception.validation.FieldValidationErrorCode import FieldValidationErrorCode
from the_music_tree_api_kit.field.AppCharField import AppCharField

from ...CriteriaSide import CriteriaSide
from ...Fields import Fields


class AbstractGenreCriteria(models.Model):
    """
    Abstract mixin carrying the `side` column, meant to be combined -- via real Django
    multi-table inheritance in a *consumer* repo -- with that consumer's concrete
    `Criteria` model to form its concrete `Genre` model:

        class Genre(AbstractGenreCriteria, Criteria):
            criteria = PrivateOneToOneField(Criteria, on_delete=models.CASCADE, parent_link=True, ...)
            objects: GenreManager = GenreManager()

    List this mixin *first* in the concrete class's bases (same convention as
    `AbstractCriteriaPlaylist`/`AbstractManualPlaylist`): its `_prepare_save` chains
    into `AbstractCriteria._prepare_save` via `super()`, so it must resolve before it
    in the MRO for the `side` validation below to actually run on save.

    `side` only ever exists as a column on a real Genre-subtype row -- there is no
    `side` column on the shared `Criteria` table at all -- so "side is genre-only" is
    now guaranteed by the schema, not by a runtime type check like the old
    `AbstractCriteria._validate_side` used to enforce. This mixin only re-validates
    the two rules that MTI cannot express structurally: placement (pop only on a
    root's direct child) and sibling uniqueness (at most one pop child per root).

    This class has no `parent`/`root`/`pk` fields of its own -- it relies entirely on
    the concrete class's inherited `AbstractCriteria` fields being present at runtime.
    """

    side = AppCharField(max_length=4, choices=CriteriaSide.choices, null=True, blank=True, db_column=Fields.SIDE)
    """
    Meaningful only when this criteria is a root criteria's direct child
    (`parent_id == root_id`); ignored elsewhere. Null/unset means "core" (the
    required, non-pop branch); `CriteriaSide.POP` marks the optional pop/crossover
    branch. See `_validate_side` for the placement and uniqueness constraints
    enforced on save.
    """

    class Meta:
        abstract = True

    if TYPE_CHECKING:
        # Provided at runtime by the concrete class's `AbstractCriteria` base via MTI;
        # declared here only so type checkers accept the `self.*` references below.
        parent_id: Any
        root_id: Any
        pk: Any

    def _validate_side(self) -> None:
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
        kwargs = super()._prepare_save(ctx)  # type: ignore[misc]
        self._validate_side()
        return kwargs
