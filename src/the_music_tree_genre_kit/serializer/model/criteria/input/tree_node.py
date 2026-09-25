from django.conf import settings
from django.core.validators import RegexValidator
from rest_framework.serializers import ChoiceField, DictField
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException
from the_music_tree_api_kit.exception.validation.FieldValidationErrorCode import FieldValidationErrorCode
from the_music_tree_api_kit.serializer.AppInputSerializer import AppInputSerializer
from the_music_tree_api_kit.serializer.field.AppCharField import AppCharField
from the_music_tree_api_kit.serializer.field.AppListField import AppListField

from the_music_tree_genre_kit.criteria.CriteriaSide import CriteriaSide
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_import.Fields import Fields


class CriteriaTreeNodeSerializer(AppInputSerializer):
    name = AppCharField(max_length=settings.CRITERIA_NAME_LEN_MAX, allow_blank=False, required=True)
    children = AppListField(child=DictField(), required=False, default=list, allow_null=True)
    side = ChoiceField(choices=CriteriaSide.choices, required=False, allow_null=True)
    summary = AppCharField(required=False, allow_null=True, allow_blank=True)
    id = AppCharField(required=False, allow_null=True, validators=[RegexValidator(r"^(Q\d+|LOCAL:[a-z0-9-]+)$")])
    primary_parents = AppListField(child=AppCharField(allow_blank=False), required=False, default=list)
    secondary_parents = AppListField(child=AppCharField(allow_blank=False), required=False, default=list)

    def __init__(self, structure_field_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.structure_field_name = structure_field_name

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise AppValidationException(
                field_name=self.structure_field_name,
                message="Invalid tree structure: each node must be a dictionary",
                field_validation_error_code=FieldValidationErrorCode.TREE_MALFORMED,
            )
        return super().to_internal_value(data)

    def validate_children(self, value):
        # Handle None values by converting to empty list
        if value is None:
            return []

        if not isinstance(value, list):
            raise ValueError(f"{Fields.CHILDREN} must be an array")

        # Structural check only -- each child's full validation (including its own
        # descendants) is performed by TreeField.run_validation's explicit recursion,
        # not here. Fully validating descendants in this field validator too would
        # mean every subtree gets re-validated once per ancestor level.
        for child in value:
            if not isinstance(child, dict):
                raise ValueError(f"{Fields.CHILDREN} must be an array of objects")

        return value
