from django.conf import settings
from rest_framework.serializers import CharField, ChoiceField, ListField, Serializer
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException
from the_music_tree_api_kit.exception.validation.FieldValidationErrorCode import FieldValidationErrorCode
from the_music_tree_api_kit.serializer.AppInputSerializer import AppInputSerializer

from the_music_tree_genre_kit.criteria.CriteriaTreeName import CriteriaTreeName
from the_music_tree_genre_kit.serializer.field.TreeField import TreeField
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_import.Fields import Fields
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_node import OVERVIEW_TYPE_CURRENT


class CrossTreeSecondaryParentsSerializer(Serializer):
    id = CharField()
    secondary_parents = ListField(child=CharField(), allow_empty=False)


class CriteriaTreeImportSerializer(AppInputSerializer):
    tree_name = ChoiceField(choices=CriteriaTreeName.choices, required=True)
    tree: TreeField = TreeField(allow_empty=False, max_nodes_count=settings.CRITERIA_TREE_IMPORT_MAX_TOTAL_COUNT)
    cross_tree_secondary_parents = CrossTreeSecondaryParentsSerializer(many=True, required=False)

    def validate(self, attrs):
        self._check_umbrellas(attrs[Fields.TREE])
        return attrs

    @staticmethod
    def _check_umbrellas(tree: list) -> None:
        # Whole-tree check: a historical overview may be an umbrella through another node's primary_parents
        # rather than a nested child, which no single node can see.
        referenced: set[str] = set()
        umbrellas: list[dict] = []
        stack = list(tree)
        while stack:
            node = stack.pop()
            stack.extend(node.get(Fields.CHILDREN) or [])
            referenced.update(node.get(Fields.PRIMARY_PARENTS) or [])
            if node.get(Fields.IS_UMBRELLA):
                umbrellas.append(node)
        for node in umbrellas:
            if node.get(Fields.OVERVIEW_TYPE) == OVERVIEW_TYPE_CURRENT or node.get(Fields.CHILDREN):
                continue
            if node.get(Fields.ID) in referenced:
                continue
            raise AppValidationException(
                field_name=Fields.CHILDREN,
                message=f"Umbrella node {node.get(Fields.NAME_PUBLIC)!r} must have at least one child",
                field_validation_error_code=FieldValidationErrorCode.TREE_MALFORMED,
            )
