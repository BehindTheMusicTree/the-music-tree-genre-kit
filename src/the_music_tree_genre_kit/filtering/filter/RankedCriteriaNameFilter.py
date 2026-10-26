from django.db.models import Case, IntegerField, Value, When
from the_music_tree_api_kit.base.BaseQuerySet import BaseQuerySet
from the_music_tree_api_kit.filtering.filter.char.NonEmptiableCharFilter import NonEmptiableCharFilter


class RankedCriteriaNameFilter(NonEmptiableCharFilter):
    """Matches names containing the value, best matches first: exact, then prefix, then the rest alphabetically.

    Without ranking, a capped page of an alphabetical list drops short exact matches ("Techno" after "Acid techno").
    """

    def filter(self, qs: BaseQuerySet, value: str) -> BaseQuerySet:
        filtered = super().filter(qs, value)
        if not value or filtered is qs:
            return filtered

        rank = Case(
            When(**{f"{self.field_name}__iexact": value}, then=Value(0)),
            When(**{f"{self.field_name}__istartswith": value}, then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
        return filtered.annotate(match_rank=rank).order_by("match_rank", self.field_name, "pk")
