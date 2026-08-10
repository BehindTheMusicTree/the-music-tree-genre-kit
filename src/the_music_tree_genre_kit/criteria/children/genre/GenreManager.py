from the_music_tree_genre_kit.criteria.AbstractCriteriaManager import AbstractCriteriaManager
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks


class GenreManager(AbstractCriteriaManager):
    def _get_criteria_type(self) -> CriteriaType:
        return CriteriaType(pk=CriteriaTypePks.GENRE)
