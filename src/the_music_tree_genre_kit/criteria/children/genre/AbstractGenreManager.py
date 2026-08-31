from django.db import models

from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks


class AbstractGenreManager(models.Manager):
    """
    Abstract manager mixin scoping a consumer's concrete `Genre` model (a real MTI
    subclass of both this mixin's sibling `AbstractGenreCriteria` and the consumer's
    concrete `Criteria`) to genre-type rows only. Combine with the consumer's own
    `CriteriaManager` (which owns tree-structure logic via `AbstractCriteriaManager`),
    listing this mixin first so its `_get_criteria_type` override wins over
    `CriteriaManager`'s own default:

        class GenreManager(AbstractGenreManager, CriteriaManager):
            pass
    """

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().filter(type_id=int(CriteriaTypePks.GENRE))

    def _get_criteria_type(self) -> CriteriaType:
        return CriteriaType(pk=int(CriteriaTypePks.GENRE))
