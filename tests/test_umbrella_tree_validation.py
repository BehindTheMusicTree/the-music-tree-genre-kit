"""An umbrella needs a child, except a current overview, which groups the sub-genres of a place that exists today."""

import pytest
from rest_framework.exceptions import ValidationError

from the_music_tree_genre_kit.serializer.model.criteria.input.tree_import.schema import load_genre_tree_schema
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_import.serializer import (
    CriteriaTreeImportSerializer,
)


def _validate(tree: list) -> list:
    serializer = CriteriaTreeImportSerializer(data={"tree_name": "regional", "tree": tree})
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data["tree"]


def _umbrella(**extra) -> dict:
    return {"id": "Q1", "name": "Brittany", "is_umbrella": True, "children": [], **extra}


def test_current_umbrella_without_child_is_accepted():
    assert _validate([_umbrella(overview_type="current")])


def test_historical_umbrella_through_primary_parents_only_is_accepted():
    tree = [
        _umbrella(id="Q1", overview_type="historical"),
        {"id": "Q2", "name": "Child", "children": [], "primary_parents": ["Q1"]},
    ]

    assert _validate(tree)


def test_historical_umbrella_referenced_from_a_nested_node_is_accepted():
    tree = [
        {"id": "Q3", "name": "Root", "children": [{"id": "Q2", "name": "Child", "primary_parents": ["Q1"]}]},
        _umbrella(id="Q1", overview_type="historical"),
    ]

    assert _validate(tree)


@pytest.mark.parametrize("extra", [{"overview_type": "historical"}, {}])
def test_umbrella_without_child_is_rejected(extra):
    with pytest.raises(ValidationError):
        _validate([_umbrella(**extra)])


def test_umbrella_with_nested_child_is_accepted():
    assert _validate([_umbrella(children=[{"id": "Q2", "name": "Child"}])])


def test_unknown_overview_type_is_rejected():
    with pytest.raises(ValidationError):
        _validate([_umbrella(overview_type="medieval")])


def test_schema_accepts_umbrella_without_child_and_declares_overview_type():
    node = load_genre_tree_schema()["$defs"]["node"]

    assert node["properties"]["overviewType"]["enum"] == ["current", "historical"]
    assert "if" not in node


def test_umbrella_referencing_itself_is_rejected():
    with pytest.raises(ValidationError):
        _validate([_umbrella(id="Q1", overview_type="historical", primary_parents=["Q1"])])


@pytest.mark.parametrize("field", ["secondary_parents"])
def test_secondary_parents_do_not_make_an_umbrella_valid(field):
    tree = [
        _umbrella(id="Q1", overview_type="historical"),
        {"id": "Q2", "name": "Child", "children": [], field: ["Q1"]},
    ]

    with pytest.raises(ValidationError):
        _validate(tree)
