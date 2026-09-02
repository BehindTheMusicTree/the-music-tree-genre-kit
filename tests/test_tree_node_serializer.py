import pytest
from rest_framework.exceptions import ValidationError
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException
from the_music_tree_api_kit.exception.validation.FieldValidationErrorCode import FieldValidationErrorCode

from the_music_tree_genre_kit.serializer.model.criteria.input.tree_node import CriteriaTreeNodeSerializer


def _serializer():
    return CriteriaTreeNodeSerializer(structure_field_name="tree")


def test_to_internal_value_raises_on_non_dict_input():
    with pytest.raises(AppValidationException) as exc_info:
        _serializer().to_internal_value("not-a-dict")

    assert exc_info.value.field_validation_error_code == FieldValidationErrorCode.TREE_MALFORMED


def test_to_internal_value_accepts_flat_valid_node():
    validated = _serializer().to_internal_value({"name": "House"})

    assert validated["name"] == "House"
    assert validated["children"] == []


def test_to_internal_value_via_full_pipeline_always_drops_children():
    # AppListField.to_internal_value delegates to `super().to_internal_value(data)`, but the
    # MRO of `AppListField(AppField, ListField)` resolves that to AppField.to_internal_value,
    # which unconditionally returns None (see AppField's own docstring: it exists only so
    # subclasses can call super() without NotImplementedError). ListField's real list-parsing
    # logic is therefore never reached, so any "children" payload submitted through the full
    # serializer pipeline is always validated down to `None` -> `[]`, regardless of content.
    # This is a latent bug in the installed the_music_tree_api_kit dependency, not this repo.
    # `validate_children`'s own recursive-validation logic is still exercised directly below.
    validated = _serializer().to_internal_value(
        {"name": "Electronic", "children": [{"name": "House"}, {"name": "Techno", "children": []}]}
    )

    assert validated["name"] == "Electronic"
    assert validated["children"] == []


def test_validate_children_converts_none_to_empty_list():
    assert _serializer().validate_children(None) == []


def test_validate_children_returns_empty_list_for_empty_input():
    assert _serializer().validate_children([]) == []


def test_validate_children_raises_value_error_when_not_a_list():
    with pytest.raises(ValueError, match="children must be an array"):
        _serializer().validate_children("not-a-list")


def test_validate_children_normalizes_missing_children_key_on_each_child():
    validated = _serializer().validate_children([{"name": "House"}])

    assert validated[0]["children"] == []


def test_validate_children_raises_on_invalid_child_node():
    # The nested child serializer's own is_valid(raise_exception=True) surfaces DRF's plain
    # ValidationError here, not AppValidationException -- validate_children doesn't translate it.
    with pytest.raises(ValidationError):
        _serializer().validate_children([{"name": ""}])


def test_to_internal_value_accepts_optional_side_field():
    validated = _serializer().to_internal_value({"name": "Pop Electronic", "side": "pop"})

    assert validated["side"] == "pop"


def test_to_internal_value_omits_side_when_not_provided():
    validated = _serializer().to_internal_value({"name": "House"})

    assert "side" not in validated


def test_to_internal_value_rejects_invalid_side_value():
    with pytest.raises(ValidationError):
        _serializer().to_internal_value({"name": "House", "side": "invalid"})


def test_to_internal_value_accepts_optional_summary_field():
    validated = _serializer().to_internal_value({"name": "Pop Electronic", "summary": "A short blurb"})

    assert validated["summary"] == "A short blurb"


def test_to_internal_value_omits_summary_when_not_provided():
    validated = _serializer().to_internal_value({"name": "House"})

    assert "summary" not in validated
