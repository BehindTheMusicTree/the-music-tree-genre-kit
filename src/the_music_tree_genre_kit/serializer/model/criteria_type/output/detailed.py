from rest_framework import serializers

from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType

from .Fields import Fields


class CriteriaTypeDetailedSerializer(serializers.ModelSerializer):
    class Meta:
        model = CriteriaType
        fields = [Fields.LABEL]
