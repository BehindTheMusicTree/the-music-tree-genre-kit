from the_music_tree_genre_kit.criteria.AbstractCriteriaManager import AbstractCriteriaManager
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType


class CriteriaManager(AbstractCriteriaManager):
    def _get_criteria_type(self) -> CriteriaType:
        return CriteriaType.objects.get_or_create(label="fixture-criteria-type")[0]
