from enum import StrEnum
from typing import Any

from django.db.models import Q, QuerySet
from rest_framework.exceptions import ValidationError


class CriteriaCoverage(StrEnum):
    ONLY = "genre_only"
    AND_DESCENDANTS = "genre_and_subgenres"


def parse_coverage(value: str | None, *, criteria_selected: bool = True) -> CriteriaCoverage:
    """Parse the wire value; an omitted value retains inclusive selection."""
    if value is None:
        return CriteriaCoverage.AND_DESCENDANTS
    if not criteria_selected:
        raise ValidationError({"coverage": "Coverage requires a genre selection."})
    try:
        return CriteriaCoverage(value)
    except ValueError:
        raise ValidationError({"coverage": "Invalid coverage."}) from None


def criteria_selection_predicate(
    criteria_id: Any,
    coverage: CriteriaCoverage,
    criteria_queryset: QuerySet,
    *,
    criteria_field: str = "genre_id",
) -> Q:
    """Select exact criteria or its primary closure without joining and duplicating tracks.

    Pass a concrete, appropriately scoped criteria queryset. The caller must also scope
    the track or membership queryset to the desired owner and population.
    """
    if not isinstance(coverage, CriteriaCoverage):
        raise ValueError("Invalid criteria coverage")
    if criteria_id is None:
        return Q(**{criteria_field: None})
    selected = criteria_queryset.filter(pk=criteria_id).values("pk")
    if coverage == CriteriaCoverage.ONLY:
        return Q(**{f"{criteria_field}__in": selected})
    closure = criteria_queryset.filter(Q(pk__in=selected) | Q(ascendants__pk__in=selected)).values("pk")
    return Q(**{f"{criteria_field}__in": closure})
