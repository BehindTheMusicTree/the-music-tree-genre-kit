from the_music_tree_genre_kit.private.PrivateModel import PrivateModel
from the_music_tree_genre_kit.public_standard_resource.PublicStandardResource import PublicStandardResource
from the_music_tree_genre_kit.uuid.UuidModel import UuidModel


class PrivateUniqueResource(PrivateModel, UuidModel, PublicStandardResource):
    class Meta:
        abstract = True
