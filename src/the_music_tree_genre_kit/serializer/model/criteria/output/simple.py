from rest_framework import serializers
from the_music_tree_api_kit.serializer.AppInputSerializer import AppInputSerializer

from the_music_tree_genre_kit.criteria.AbstractCriteria import AbstractCriteria
from the_music_tree_genre_kit.serializer.model.criteria.output.minimum import build_criteria_minimum_serializer

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
    ]
    # `side` only exists on a concrete Genre subtype (see `AbstractGenreCriteria`), not
    # on the shared `AbstractCriteria` table -- only expose it when the model has it.
    if any(field.name == CriteriaOutputFieldKey.SIDE.value for field in criteria_model._meta.get_fields()):
        serializer_fields.append(CriteriaOutputFieldKey.SIDE.value)

    class CriteriaSimpleSerializer(AppInputSerializer, serializers.ModelSerializer):
        parent = minimum_serializer_class()

        class Meta:
            model = criteria_model
            fields = serializer_fields

    return CriteriaSimpleSerializer
