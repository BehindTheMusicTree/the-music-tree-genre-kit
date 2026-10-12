from the_music_tree_api_kit.filtering.filter.char.NonEmptiableCharFilter import NonEmptiableCharFilter
from the_music_tree_api_kit.filtering.filter.foreign_key.DescendantAwareFilter import DescendantAwareFilter
from the_music_tree_api_kit.filtering.set.private_unique_resource.PrivateUniqueResourceFilterSet import (
    PrivateUniqueResourceFilterSet,
)

from the_music_tree_genre_kit.criteria.Fields import Fields


class CriteriaFilterSet(PrivateUniqueResourceFilterSet):
    # Criteria stores its name in `_name` (db_column="name"); "name" is a property, not an ORM field.
    name = NonEmptiableCharFilter(
        field_name=Fields.NAME_INTERNAL, field_name_public=Fields.NAME_PUBLIC, lookup_expr="icontains"
    )
    parent = DescendantAwareFilter()

    class Meta:
        fields = [Fields.NAME_PUBLIC, Fields.PARENT, *PrivateUniqueResourceFilterSet.get_date_fields()]
