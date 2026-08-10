from the_music_tree_genre_kit.criteria.lineage_rel.AbstractCriteriaLineageRel import AbstractCriteriaLineageRel
from the_music_tree_genre_kit.serializer.model.criteria.output.minimum import CriteriaMinimumSerializer
from the_music_tree_genre_kit.serializer.model.criteria_lineage_rel.detailed import CriteriaLineageRelDetailedSerializer
from the_music_tree_genre_kit.serializer.model.criteria_lineage_rel.Fields import Fields as AvailableFields


class Fields:
    ASCENDANT = AvailableFields.ASCENDANT
    DEGREE = AvailableFields.DEGREE


class CriteriaLineageRelWithoutDescendantSerializer(CriteriaLineageRelDetailedSerializer):
    ascendant = CriteriaMinimumSerializer()

    class Meta:
        model = AbstractCriteriaLineageRel
        fields = [Fields.ASCENDANT, Fields.DEGREE]
