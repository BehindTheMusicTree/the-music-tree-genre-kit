from rest_framework import serializers

from the_music_tree_genre_kit.criteria.AbstractCriteria import AbstractCriteria
from the_music_tree_genre_kit.criteria.lineage_rel.AbstractCriteriaLineageRel import AbstractCriteriaLineageRel
from the_music_tree_genre_kit.serializer.model.criteria.output.minimum import build_criteria_minimum_serializer
from the_music_tree_genre_kit.serializer.model.criteria_lineage_rel.Fields import Fields


def build_criteria_lineage_rel_detailed_serializer(
    lineage_rel_model: type[AbstractCriteriaLineageRel],
    criteria_model: type[AbstractCriteria],
) -> type[serializers.ModelSerializer]:
    minimum_serializer_class = build_criteria_minimum_serializer(criteria_model)

    class CriteriaLineageRelDetailedSerializer(serializers.ModelSerializer):
        descendant = minimum_serializer_class()
        ascendant = minimum_serializer_class()

        class Meta:
            model = lineage_rel_model
            fields = [Fields.DESCENDANT, Fields.ASCENDANT, Fields.DEGREE]

    return CriteriaLineageRelDetailedSerializer
