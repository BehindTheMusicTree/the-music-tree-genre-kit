from django.apps import apps
from django.conf import settings
from django.db.models import Case, Q, Value, When
from the_music_tree_api_kit.base.BaseQuerySet import BaseQuerySet
from the_music_tree_api_kit.field.AppCharField import AppCharField
from the_music_tree_api_kit.filtering.filter.char.NonEmptiableCharFilter import NonEmptiableCharFilter

from the_music_tree_genre_kit.criteria.Fields import Fields as CriteriaFields
from the_music_tree_genre_kit.criteria.playlist.CriterialessPlaylistNames import CriterialessPlaylistNames
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks


class CriteriaNameFilter(NonEmptiableCharFilter):
    """Filters criteria playlists by criteria name, matching criterialess playlists by their display name."""

    def filter(self, qs: BaseQuerySet, value: str) -> BaseQuerySet:
        if not value:
            return super().filter(qs, value)

        special_name = Case(
            When(type__pk=CriteriaTypePks.GENRE, then=Value(CriterialessPlaylistNames.GENRE)),
            When(type__pk=CriteriaTypePks.TAG, then=Value(CriterialessPlaylistNames.TAG)),
            output_field=AppCharField(),
        )
        special_names_filter = Q(criteria__isnull=True) & Q(type__pk__in=[CriteriaTypePks.GENRE, CriteriaTypePks.TAG])

        criteria_model = apps.get_model(settings.CRITERIA_MODEL)
        criteria_name_filter = Q(criteria__isnull=False) & Q(
            criteria__uuid__in=criteria_model.objects.filter(
                **{f"{CriteriaFields.NAME_INTERNAL}__icontains": value}
            ).values("uuid")
        )

        return qs.annotate(special_name=special_name).filter(
            (special_names_filter & Q(special_name__icontains=value.lower())) | criteria_name_filter
        )
