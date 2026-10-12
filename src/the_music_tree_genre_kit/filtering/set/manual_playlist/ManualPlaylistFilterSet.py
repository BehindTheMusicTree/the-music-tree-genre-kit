from the_music_tree_api_kit.filtering.filter.char.NonEmptiableCharFilter import NonEmptiableCharFilter
from the_music_tree_api_kit.filtering.set.private_unique_resource.PrivateUniqueResourceFilterSet import (
    PrivateUniqueResourceFilterSet,
)

from the_music_tree_genre_kit.manual_playlist.Fields import Fields


class ManualPlaylistFilterSet(PrivateUniqueResourceFilterSet):
    name = NonEmptiableCharFilter(
        field_name=Fields.NAME_INTERNAL, field_name_public=Fields.NAME_PUBLIC, lookup_expr="icontains"
    )

    class Meta:
        fields = [Fields.NAME_PUBLIC, *PrivateUniqueResourceFilterSet.get_date_fields()]
