from rest_framework import serializers
from the_music_tree_api_kit.serializer.AppInputSerializer import AppInputSerializer

from the_music_tree_genre_kit.criteria.AbstractCriteria import AbstractCriteria

from .CriteriaOutputFieldKey import CriteriaOutputFieldKey


def build_criteria_minimum_serializer(
    criteria_model: type[AbstractCriteria],
) -> type[serializers.ModelSerializer]:
    """DRF's ModelSerializer rejects an abstract Meta.model, so each consumer must supply its own concrete subclass."""

    class CriteriaMinimumSerializer(AppInputSerializer, serializers.ModelSerializer):
        class Meta:
            model = criteria_model
            fields = [
                CriteriaOutputFieldKey.UUID.value,
                CriteriaOutputFieldKey.NAME.value,
            ]

    return CriteriaMinimumSerializer
