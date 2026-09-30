from rest_framework import serializers
from the_music_tree_api_kit.serializer.AppInputSerializer import AppInputSerializer
from the_music_tree_api_kit.serializer.EagerLoadingMixin import EagerLoadingMixin

from the_music_tree_genre_kit.criteria.AbstractCriteria import AbstractCriteria
from the_music_tree_genre_kit.serializer.model.criteria.output.minimum import build_criteria_minimum_serializer
from the_music_tree_genre_kit.serializer.model.criteria.output.side import CriteriaSideSerializerMixin

from .CriteriaOutputFieldKey import CriteriaOutputFieldKey


def build_criteria_simple_serializer(
    criteria_model: type[AbstractCriteria],
) -> type[serializers.ModelSerializer]:
    minimum_serializer_class = build_criteria_minimum_serializer(criteria_model)

    serializer_fields = [
        CriteriaOutputFieldKey.UUID.value,
        CriteriaOutputFieldKey.NAME.value,
        CriteriaOutputFieldKey.PARENT.value,
        CriteriaOutputFieldKey.CREATED_ON.value,
        CriteriaOutputFieldKey.SIDE.value,
        CriteriaOutputFieldKey.SUMMARY.value,
        CriteriaOutputFieldKey.TREE_NAME.value,
        CriteriaOutputFieldKey.PRIMARY_PARENTS.value,
        CriteriaOutputFieldKey.SECONDARY_PARENTS.value,
    ]

    # `side` is a real column only on the concrete Genre subtype (see
    # `AbstractGenreCriteria`), not on the shared `AbstractCriteria` table -- when the
    # model doesn't have it natively, mix in the reverse-accessor resolver instead.
    has_own_side_field = any(
        field.name == CriteriaOutputFieldKey.SIDE.value for field in criteria_model._meta.get_fields()
    )
    bases = (
        (AppInputSerializer, serializers.ModelSerializer)
        if has_own_side_field
        else (CriteriaSideSerializerMixin, AppInputSerializer, serializers.ModelSerializer)
    )

    class CriteriaSimpleSerializer(EagerLoadingMixin, *bases):
        parent = minimum_serializer_class()
        primary_parents = minimum_serializer_class(many=True, read_only=True)
        secondary_parents = minimum_serializer_class(many=True, read_only=True)

        @classmethod
        def setup_queryset(cls, queryset, prefix=""):
            queryset = queryset.select_related(f"{prefix}parent").prefetch_related(
                f"{prefix}additional_primary_parents", f"{prefix}secondary_parents"
            )
            # Decided from the queryset, not `criteria_model`: a consumer may hand this serializer a
            # queryset of a concrete subtype (e.g. `Genre`, whose `side` is its own column).
            model = queryset.model
            for name in filter(None, prefix.split("__")):
                model = model._meta.get_field(name).related_model
            if any(field.name == "genre" for field in model._meta.get_fields()):
                return queryset.select_related(f"{prefix}genre")
            return queryset

        class Meta:
            model = criteria_model
            fields = serializer_fields

    return CriteriaSimpleSerializer
