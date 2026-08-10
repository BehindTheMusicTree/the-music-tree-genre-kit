from rest_framework import serializers

from the_music_tree_genre_kit.criteria.lineage_rel.AbstractCriteriaLineageRel import AbstractCriteriaLineageRel
from the_music_tree_genre_kit.serializer.model.criteria.output.minimum import CriteriaMinimumSerializer
from the_music_tree_genre_kit.serializer.model.criteria_lineage_rel.Fields import Fields


class CriteriaLineageRelDetailedSerializer(serializers.ModelSerializer):
    descendant = CriteriaMinimumSerializer()
    ascendant = CriteriaMinimumSerializer()

    class Meta:
        model = AbstractCriteriaLineageRel
        fields = [Fields.DESCENDANT, Fields.ASCENDANT, Fields.DEGREE]
