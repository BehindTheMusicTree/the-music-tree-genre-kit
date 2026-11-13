"""The Gold genre-tree JSON Schema is checked against the serializers that implement its contract."""

import pytest

from the_music_tree_genre_kit.serializer.model.criteria.input.tree_import.schema import load_genre_tree_schema
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_import.serializer import (
    CriteriaTreeImportSerializer,
)
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_node import CriteriaTreeNodeSerializer


@pytest.fixture(scope="module")
def schema() -> dict:
    return load_genre_tree_schema()


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


def _required_wire_names(serializer) -> set[str]:
    return {_camel(name) for name, field in serializer.fields.items() if field.required}


def test_schema_declares_this_package_as_its_id(schema):
    assert "the-music-tree-genre-kit" in schema["$id"]


def test_required_fields_are_required_by_schema(schema):
    file_required = _required_wire_names(CriteriaTreeImportSerializer())
    node_required = _required_wire_names(CriteriaTreeNodeSerializer(structure_field_name="tree"))

    assert file_required <= set(schema["required"])
    assert node_required <= set(schema["$defs"]["node"]["required"])


def test_serializer_fields_are_declared_by_schema(schema):
    # The schema sets additionalProperties=false, so a serializer field it does not declare would be rejected.
    file_fields = {_camel(name) for name in CriteriaTreeImportSerializer().fields}
    node_fields = {_camel(name) for name in CriteriaTreeNodeSerializer(structure_field_name="tree").fields}

    assert file_fields <= set(schema["properties"])
    assert node_fields <= set(schema["$defs"]["node"]["properties"])
