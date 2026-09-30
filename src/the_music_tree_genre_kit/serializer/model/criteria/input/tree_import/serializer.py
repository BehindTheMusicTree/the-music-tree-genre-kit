from django.conf import settings
from rest_framework.serializers import ChoiceField
from the_music_tree_api_kit.serializer.AppInputSerializer import AppInputSerializer

from the_music_tree_genre_kit.criteria.CriteriaTreeName import CriteriaTreeName
from the_music_tree_genre_kit.serializer.field.TreeField import TreeField


class CriteriaTreeImportSerializer(AppInputSerializer):
    tree_name = ChoiceField(choices=CriteriaTreeName.choices, required=True)
    tree: TreeField = TreeField(allow_empty=False, max_nodes_count=settings.CRITERIA_TREE_IMPORT_MAX_TOTAL_COUNT)
