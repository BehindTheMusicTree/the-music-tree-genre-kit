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


def test_to_internal_value_via_full_pipeline_keeps_children():
    # Regression: AppListField used to resolve `super().to_internal_value` to a sink returning
    # None (api-kit < 0.12.1), which silently emptied every list field.
    children = [{"name": "House"}, {"name": "Techno", "children": []}]

    validated = _serializer().to_internal_value({"name": "Electronic", "children": children})

    assert validated["name"] == "Electronic"
    assert validated["children"] == children


def test_to_internal_value_keeps_primary_and_secondary_parents():
    validated = _serializer().to_internal_value(
        {
            "name": "Music of Ireland",
            "id": "Q1378776",
            "primary_parents": ["Q7482056"],
            "secondary_parents": ["Q188451", "Q8134"],
        }
    )

    assert validated["primary_parents"] == ["Q7482056"]
    assert validated["secondary_parents"] == ["Q188451", "Q8134"]


def test_to_internal_value_rejects_blank_parent_id():
    with pytest.raises(ValidationError) as exc_info:
        _serializer().to_internal_value({"name": "House", "primary_parents": [""]})

    converted = AppValidationException._detect_and_convert_from_drf_exception(exc_info.value)
    assert converted is not None
    assert converted.field == "primary_parents"
    assert converted.errors["primary_parents"]["code"] == FieldValidationErrorCode.BLANK


def test_validate_children_converts_none_to_empty_list():
    assert _serializer().validate_children(None) == []


def test_validate_children_returns_empty_list_for_empty_input():
    assert _serializer().validate_children([]) == []


def test_validate_children_raises_value_error_when_not_a_list():
    with pytest.raises(ValueError, match="children must be an array"):
        _serializer().validate_children("not-a-list")


def test_validate_children_passes_through_child_dicts_unvalidated():
    # Full per-child validation (including "children" key normalization) is performed by
    # TreeField.run_validation's own explicit recursion, not here -- see TreeField.py. Doing it
    # here too would mean every subtree gets fully re-validated once per ancestor level.
    validated = _serializer().validate_children([{"name": "House"}])

    assert "children" not in validated[0]


def test_validate_children_raises_on_non_dict_child_node():
    with pytest.raises(ValueError, match="children must be an array of objects"):
        _serializer().validate_children(["not-a-dict"])


def test_to_internal_value_accepts_optional_side_field():
    validated = _serializer().to_internal_value({"name": "Pop Electronic", "side": "pop"})

    assert validated["side"] == "pop"


def test_to_internal_value_omits_side_when_not_provided():
    validated = _serializer().to_internal_value({"name": "House"})

    assert "side" not in validated


def test_to_internal_value_accepts_optional_id_field():
    validated = _serializer().to_internal_value({"name": "Electronic", "id": "Q9759"})

    assert validated["id"] == "Q9759"


def test_to_internal_value_accepts_local_synthetic_id():
    validated = _serializer().to_internal_value({"name": "Core Electronic", "id": "LOCAL:core-electronic"})

    assert validated["id"] == "LOCAL:core-electronic"


def test_to_internal_value_omits_id_when_not_provided():
    validated = _serializer().to_internal_value({"name": "House"})

    assert "id" not in validated


def test_to_internal_value_rejects_malformed_wikidata_id():
    with pytest.raises(ValidationError):
        _serializer().to_internal_value({"name": "House", "id": "not-a-qid"})


def test_to_internal_value_rejects_invalid_side_value():
    with pytest.raises(ValidationError):
        _serializer().to_internal_value({"name": "House", "side": "invalid"})


def test_to_internal_value_accepts_optional_summary_field():
    validated = _serializer().to_internal_value({"name": "Pop Electronic", "summary": "A short blurb"})

    assert validated["summary"] == "A short blurb"


def test_to_internal_value_omits_summary_when_not_provided():
    validated = _serializer().to_internal_value({"name": "House"})

    assert "summary" not in validated


def test_validate_rejects_summary_source_url_without_summary():
    with pytest.raises(AppValidationException) as exc_info:
        _serializer().run_validation(
            {"name": "House", "summary": "", "summary_source_url": "https://en.wikipedia.org/wiki/House_music"}
        )

    assert exc_info.value.field_validation_error_code == FieldValidationErrorCode.REQUIRED


def test_validate_accepts_summary_source_url_with_summary():
    validated = _serializer().run_validation(
        {"name": "House", "summary": "Wiki intro.", "summary_source_url": "https://en.wikipedia.org/wiki/House_music"}
    )

    assert validated["summary_source_url"] == "https://en.wikipedia.org/wiki/House_music"


@pytest.mark.parametrize("url", ["ftp://example.com/x", "javascript:alert(1)"])
def test_validate_rejects_non_http_summary_source_url(url):
    with pytest.raises(ValidationError):
        _serializer().run_validation({"name": "House", "summary": "Wiki intro.", "summary_source_url": url})


@pytest.mark.parametrize("url", [None, ""])
def test_validate_accepts_null_and_blank_summary_source_url(url):
    validated = _serializer().run_validation({"name": "House", "summary_source_url": url})

    assert not validated["summary_source_url"]
