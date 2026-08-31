from django.db import models

from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks


class AbstractTagManager(models.Manager):
    """
    Abstract manager mixin scoping a consumer's concrete `Tag` model to tag-type rows
    only. Combine with the consumer's own `CriteriaManager` (which owns tree-structure
    logic via `AbstractCriteriaManager`), listing this mixin first so its
    `_get_criteria_type` override wins over `CriteriaManager`'s own default:

        class TagManager(AbstractTagManager, CriteriaManager):
            pass
    """

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().filter(type_id=int(CriteriaTypePks.TAG))

    def _get_criteria_type(self) -> CriteriaType:
        return CriteriaType(pk=int(CriteriaTypePks.TAG))
