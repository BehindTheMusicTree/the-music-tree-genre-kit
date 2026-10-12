from functools import reduce
from operator import or_

from django.db.models.query import QuerySet
from the_music_tree_api_kit.filtering.filter.char.NonEmptiableCharFilter import NonEmptiableCharFilter
from the_music_tree_api_kit.filtering.filter.char.OptionalEnumCharFilter import OptionalEnumCharFilter
from the_music_tree_api_kit.filtering.set.private_unique_resource.PrivateUniqueResourceFilterSet import (
    PrivateUniqueResourceFilterSet,
)

from the_music_tree_genre_kit.criteria.Fields import Fields as CriteriaFields
from the_music_tree_genre_kit.criteria.playlist.CriterialessPlaylistNames import CriterialessPlaylistNames
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks
from the_music_tree_genre_kit.playlist.Fields import Fields
from the_music_tree_genre_kit.playlist.Playlist import Playlist
from the_music_tree_genre_kit.playlist.PlaylistTypesLabel import PlaylistTypesLabel


class PlaylistFilterSet(PrivateUniqueResourceFilterSet):
    name = NonEmptiableCharFilter(method="filter_by_name_and_type")
    type = OptionalEnumCharFilter(enum_class=PlaylistTypesLabel, method="filter_by_name_and_type")

    class Meta:
        model = Playlist
        fields = [Fields.NAME_PUBLIC, Fields.TYPE_LABEL_PUBLIC, *PrivateUniqueResourceFilterSet.get_date_fields()]

    def filter_by_name_and_type(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        name_value = self.data.get(Fields.NAME_PUBLIC)
        type_label = self.data.get(Fields.TYPE_LABEL_PUBLIC)
        name_lookup = name_value if name == Fields.NAME_PUBLIC else ""

        base_queryset = queryset.order_by(Fields.CREATED_ON, "pk")

        result_querysets = []

        if type_label is None or type_label.lower() == PlaylistTypesLabel.MANUAL.lower():
            manual_qs = base_queryset.filter(
                **{
                    f"{Fields.MANUAL_PLAYLIST}__isnull": False,
                    f"{Fields.MANUAL_PLAYLIST}__{Fields.NAME_INTERNAL}__icontains": name_lookup,
                }
            )
            result_querysets.append(manual_qs)

        if type_label is None or type_label.lower() in [
            PlaylistTypesLabel.GENRE.lower(),
            PlaylistTypesLabel.TAG.lower(),
        ]:
            criteria_qs = base_queryset.filter(
                **{
                    f"{Fields.CRITERIA_PLAYLIST}__isnull": False,
                    f"{Fields.CRITERIA_PLAYLIST}__type__label__icontains": type_label.upper() if type_label else "",
                    f"{Fields.CRITERIA_PLAYLIST}__criteria__{CriteriaFields.NAME_INTERNAL}__icontains": name_lookup,
                }
            )
            result_querysets.append(criteria_qs)

        if (not name_value or name_value.lower() in CriterialessPlaylistNames.GENRE.lower()) and type_label in [
            None,
            PlaylistTypesLabel.GENRE,
        ]:
            genreless_qs = base_queryset.filter(
                criteria_playlist__isnull=False,
                criteria_playlist__criteria__isnull=True,
                criteria_playlist__type_id=CriteriaTypePks.GENRE,
            )
            result_querysets.append(genreless_qs)

        if (not name_value or name_value.lower() in CriterialessPlaylistNames.TAG.lower()) and type_label in [
            None,
            PlaylistTypesLabel.TAG,
        ]:
            tagless_qs = base_queryset.filter(
                criteria_playlist__isnull=False,
                criteria_playlist__criteria__isnull=True,
                criteria_playlist__type_id=CriteriaTypePks.TAG,
            )
            result_querysets.append(tagless_qs)

        if not result_querysets:
            return Playlist.objects.none()

        return reduce(or_, result_querysets)
