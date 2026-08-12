import pytest
from django.contrib.auth import get_user_model

from tests.fixture_app.models import Criteria, CriteriaLineageRel
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.serializer.model.criteria.output.minimum import build_criteria_minimum_serializer
from the_music_tree_genre_kit.serializer.model.criteria.output.simple import build_criteria_simple_serializer
from the_music_tree_genre_kit.serializer.model.criteria_lineage_rel.detailed import (
    build_criteria_lineage_rel_detailed_serializer,
)
from the_music_tree_genre_kit.serializer.model.criteria_lineage_rel.without_ascendant import (
    build_criteria_lineage_rel_without_ascendant_serializer,
)
from the_music_tree_genre_kit.serializer.model.criteria_lineage_rel.without_descendant import (
    build_criteria_lineage_rel_without_descendant_serializer,
)


@pytest.fixture
def criteria_tree(db):
    user = get_user_model().objects.create(username="fixture-user")
    criteria_type = CriteriaType.objects.create(label="genre")

    root = Criteria(user=user, type=criteria_type)
    root._name = "root"
    root.save()

    child = Criteria(user=user, type=criteria_type, parent=root)
    child._name = "child"
    child.save()

    lineage_rel = CriteriaLineageRel.objects.create(user=user, descendant=child, ascendant=root, degree=1)

    return root, child, lineage_rel


def test_criteria_minimum_serializer(criteria_tree):
    root, _child, _lineage_rel = criteria_tree

    serializer_class = build_criteria_minimum_serializer(Criteria)
    data = serializer_class(root).data

    assert data["uuid"] == str(root.uuid)
    assert data["name"] == "root"


def test_criteria_simple_serializer(criteria_tree):
    root, child, _lineage_rel = criteria_tree

    serializer_class = build_criteria_simple_serializer(Criteria)
    data = serializer_class(child).data

    assert data["uuid"] == str(child.uuid)
    assert data["name"] == "child"
    assert data["parent"]["uuid"] == str(root.uuid)
    assert data["parent"]["name"] == "root"


def test_criteria_lineage_rel_detailed_serializer(criteria_tree):
    root, child, lineage_rel = criteria_tree

    serializer_class = build_criteria_lineage_rel_detailed_serializer(CriteriaLineageRel, Criteria)
    data = serializer_class(lineage_rel).data

    assert data["descendant"]["uuid"] == str(child.uuid)
    assert data["ascendant"]["uuid"] == str(root.uuid)
    assert data["degree"] == 1


def test_criteria_lineage_rel_without_ascendant_serializer(criteria_tree):
    _root, child, lineage_rel = criteria_tree

    serializer_class = build_criteria_lineage_rel_without_ascendant_serializer(CriteriaLineageRel, Criteria)
    data = serializer_class(lineage_rel).data

    assert data["descendant"]["uuid"] == str(child.uuid)
    assert data["degree"] == 1
    assert "ascendant" not in data


def test_criteria_lineage_rel_without_descendant_serializer(criteria_tree):
    root, _child, lineage_rel = criteria_tree

    serializer_class = build_criteria_lineage_rel_without_descendant_serializer(CriteriaLineageRel, Criteria)
    data = serializer_class(lineage_rel).data

    assert data["ascendant"]["uuid"] == str(root.uuid)
    assert data["degree"] == 1
    assert "descendant" not in data
