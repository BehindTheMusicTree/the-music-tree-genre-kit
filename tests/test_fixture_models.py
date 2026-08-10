import pytest
from django.contrib.auth import get_user_model

from tests.fixture_app.models import Criteria, CriteriaLineageRel
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType


@pytest.mark.django_db
def test_criteria_tree_via_abstract_base():
    user = get_user_model().objects.create(username="fixture-user")
    criteria_type = CriteriaType.objects.create(label="genre")

    root = Criteria(user=user, type=criteria_type)
    root._name = "root"
    root.save()

    child = Criteria(user=user, type=criteria_type, parent=root)
    child._name = "child"
    child.save()

    CriteriaLineageRel.objects.create(user=user, descendant=child, ascendant=root, degree=1)

    assert root.is_root
    assert not child.is_root
    assert child.name == "child"
    assert set(root.descendant_list) == {root, child}
    assert child.is_descendant_of(root)
