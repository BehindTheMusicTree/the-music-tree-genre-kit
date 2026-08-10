from the_music_tree_genre_kit.serializer.field.foreign_key.PrivateUuidField import PrivateUuidField

from .AppOneToOneField import AppOneToOneField


class PrivateOneToOneField(AppOneToOneField):
    def __init__(self, to, **kwargs):
        super().__init__(to, **kwargs)
        self.serializer_field_class = PrivateUuidField
