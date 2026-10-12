from django.db.models import Q
from django_filters import ChoiceFilter
from the_music_tree_api_kit.filtering.filter.foreign_key.ForeignKeyFilter import ForeignKeyFilter
from the_music_tree_api_kit.filtering.set.private_unique_resource.PrivateUniqueResourceFilterSet import (
    PrivateUniqueResourceFilterSet,
)

from the_music_tree_genre_kit.criteria.CriteriaTreeName import CriteriaTreeName
from the_music_tree_genre_kit.criteria.Fields import Fields as CriteriaFields
from the_music_tree_genre_kit.criteria.playlist.Fields import Fields
from the_music_tree_genre_kit.filtering.filter.CriteriaNameFilter import CriteriaNameFilter


class CriteriaPlaylistFilterSet(PrivateUniqueResourceFilterSet):
    name = CriteriaNameFilter(
        field_name=f"{Fields.CRITERIA}__{CriteriaFields.NAME_INTERNAL}",
        field_name_public=CriteriaFields.NAME_PUBLIC,
        lookup_expr="icontains",
    )
    parent = ForeignKeyFilter(
        field_name=f"{Fields.CRITERIA}__{CriteriaFields.PARENT}__criteria_playlist",
        field_name_public=CriteriaFields.PARENT,
    )
    tree_name = ChoiceFilter(choices=CriteriaTreeName.choices, method="filter_tree_name")

    class Meta:
        fields = [
            CriteriaFields.NAME_PUBLIC,
            CriteriaFields.PARENT,
            CriteriaFields.TREE_NAME,
            *PrivateUniqueResourceFilterSet.get_date_fields(),
        ]

    def filter_tree_name(self, queryset, name, value):
        tree_name_filter = Q(**{f"{Fields.CRITERIA}__{name}": value})
        if value == CriteriaTreeName.CANONICAL:
            # Genreless/Tagless playlists have no criteria and belong to the canonical tree.
            tree_name_filter |= Q(**{f"{Fields.CRITERIA}__isnull": True})
        return queryset.filter(tree_name_filter)
