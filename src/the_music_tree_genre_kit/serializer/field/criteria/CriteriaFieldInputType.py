from enum import Enum

from the_music_tree_genre_kit.criteria.Fields import Fields as CriteriaFields


class CriteriaFieldInputType(Enum):
    UUID = CriteriaFields.UUID
    NAME = CriteriaFields.NAME_PUBLIC
