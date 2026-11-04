from django.conf import settings
from rest_framework.serializers import CharField, ChoiceField, ListField, Serializer
from the_music_tree_api_kit.serializer.AppInputSerializer import AppInputSerializer

from the_music_tree_genre_kit.criteria.CriteriaTreeName import CriteriaTreeName
from the_music_tree_genre_kit.serializer.field.TreeField import TreeField


class CrossTreeSecondaryParentsSerializer(Serializer):
    id = CharField()
    secondary_parents = ListField(child=CharField(), allow_empty=False)


class CriteriaTreeImportSerializer(AppInputSerializer):
    tree_name = ChoiceField(choices=CriteriaTreeName.choices, required=True)
    tree: TreeField = TreeField(allow_empty=False, max_nodes_count=settings.CRITERIA_TREE_IMPORT_MAX_TOTAL_COUNT)
    cross_tree_secondary_parents = CrossTreeSecondaryParentsSerializer(many=True, required=False)
