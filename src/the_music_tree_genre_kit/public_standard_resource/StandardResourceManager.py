from the_music_tree_genre_kit.base.BaseManager import BaseManager

from .Fields import Fields
from .PublicStandardResource import PublicStandardResource


class StandardResourceManager[T: PublicStandardResource](BaseManager):
    model: type[T]

    def get_default_ordering(self):
        return [Fields.CREATED_ON]
