from the_music_tree_genre_kit.private.PrivateModel import PrivateModel
from the_music_tree_genre_kit.public_standard_resource.PublicStandardResource import PublicStandardResource


class PrivateStandardResource(PrivateModel, PublicStandardResource):
    class Meta:
        abstract = True
