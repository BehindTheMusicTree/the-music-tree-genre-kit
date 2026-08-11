from rest_framework import serializers
from the_music_tree_api_kit.serializer.AppInputSerializer import AppInputSerializer

from the_music_tree_genre_kit.criteria.AbstractCriteria import AbstractCriteria

from .CriteriaOutputFieldKey import CriteriaOutputFieldKey


class CriteriaMinimumSerializer(AppInputSerializer, serializers.ModelSerializer):
    class Meta:
        model = AbstractCriteria
        fields = [
            CriteriaOutputFieldKey.UUID.value,
            CriteriaOutputFieldKey.NAME.value,
        ]
