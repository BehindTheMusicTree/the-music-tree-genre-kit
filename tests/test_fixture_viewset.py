import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from tests.fixture_app.models import Criteria, CriteriaPlaylist
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_node import CriteriaTreeNodeSerializer


@pytest.fixture
def user(db):
    return get_user_model().objects.create(username="fixture-user")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def criteria_type(db):
    return CriteriaType.objects.create(label="genre")


def test_tree_returns_nested_structure(api_client, user, criteria_type):
    root = Criteria(user=user, type=criteria_type)
    root._name = "root"
    root.save()

    child = Criteria(user=user, type=criteria_type, parent=root)
    child._name = "child"
    child.save()

    response = api_client.get("/criteria/tree/", {"allows_multiple_primary_parents": "false"})

    assert response.status_code == 200
    assert response.data == [
        {"name": "root", "children": [{"name": "child", "children": [], "side": None}], "side": None}
    ]


def test_tree_excludes_other_users_criteria(api_client, user, criteria_type):
    other_user = get_user_model().objects.create(username="other-user")
    other_root = Criteria(user=other_user, type=criteria_type)
    other_root._name = "other-root"
    other_root.save()

    response = api_client.get("/criteria/tree/", {"allows_multiple_primary_parents": "false"})

    assert response.status_code == 200
    assert response.data == []


def test_import_tree_creates_criteria(api_client, criteria_type):
    payload = {
        "allows_multiple_primary_parents": False,
        "tree": [{"name": "root", "children": [{"name": "child", "children": []}]}],
    }

    response = api_client.post("/criteria/tree/import/", payload, format="json")

    assert response.status_code == 201
    names = {result["name"] for result in response.data["results"]}
    assert names == {"root", "child"}


def test_import_tree_replaces_existing_criteria(api_client, user, criteria_type):
    stale = Criteria(user=user, type=criteria_type)
    stale._name = "stale"
    stale.save()
    CriteriaPlaylist.objects.create(user=user, criteria=stale, type=criteria_type)
    CriteriaPlaylist.objects.create(user=user, criteria=None, type=criteria_type)

    payload = {"allows_multiple_primary_parents": False, "tree": [{"name": "fresh", "children": []}]}

    response = api_client.post("/criteria/tree/import/", payload, format="json")

    assert response.status_code == 201
    names = {result["name"] for result in response.data["results"]}
    assert names == {"fresh"}
    assert not Criteria.objects.filter(user=user).filter(_name="stale").exists()


def test_import_tree_rejects_empty_tree(api_client, criteria_type):
    response = api_client.post(
        "/criteria/tree/import/", {"allows_multiple_primary_parents": False, "tree": []}, format="json"
    )

    assert response.status_code == 400


def test_import_tree_rejects_invalid_node_deep_in_tree(api_client, criteria_type):
    # Regression guard: validate_children on CriteriaTreeNodeSerializer no longer does a full
    # nested validation pass itself -- TreeField.run_validation's own recursion must still be
    # the one that catches an invalid node several levels down.
    payload = {
        "allows_multiple_primary_parents": False,
        "tree": [
            {
                "name": "root",
                "children": [{"name": "child", "children": [{"name": "", "children": []}]}],
            }
        ],
    }

    response = api_client.post("/criteria/tree/import/", payload, format="json")

    assert response.status_code == 400
    assert not Criteria.objects.filter(_name="root").exists()


def test_import_tree_accepts_optional_id_field(api_client, criteria_type):
    payload = {"allows_multiple_primary_parents": False, "tree": [{"name": "root", "id": "Q9759", "children": []}]}

    response = api_client.post("/criteria/tree/import/", payload, format="json")

    assert response.status_code == 201
    names = {result["name"] for result in response.data["results"]}
    assert names == {"root"}


def test_import_tree_rejects_malformed_id_field(api_client, criteria_type):
    payload = {"allows_multiple_primary_parents": False, "tree": [{"name": "root", "id": "not-a-qid", "children": []}]}

    response = api_client.post("/criteria/tree/import/", payload, format="json")

    assert response.status_code == 400


def test_import_tree_rejects_duplicate_id_across_branches(api_client, criteria_type):
    # Whole-tree scope, not just siblings: the two "Q9759" ids are on separate
    # branches, not each other's siblings, so this exercises TreeField's shared
    # `seen_ids` accumulation across the full recursion, not just one level.
    payload = {
        "allows_multiple_primary_parents": False,
        "tree": [
            {"name": "Electronic", "id": "Q9759", "children": [{"name": "House", "children": []}]},
            {"name": "Techno", "children": [{"name": "Acid Techno", "id": "Q9759", "children": []}]},
        ],
    }

    response = api_client.post("/criteria/tree/import/", payload, format="json")

    assert response.status_code == 400


def test_import_tree_validates_each_node_exactly_once(api_client, criteria_type, monkeypatch):
    # Regression guard for the double-recursion bug where validate_children fully re-validated
    # every descendant subtree in addition to TreeField.run_validation's own explicit recursion,
    # making validation cost blow up with tree depth. Without the fix, instantiation_count would
    # be quadratic in depth; with it, it's linear (one CriteriaTreeNodeSerializer per node, plus a
    # bounded constant of incidental instantiations from field binding/children_field plumbing).
    instantiation_count = 0
    original_init = CriteriaTreeNodeSerializer.__init__

    def counting_init(self, *args, **kwargs):
        nonlocal instantiation_count
        instantiation_count += 1
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(CriteriaTreeNodeSerializer, "__init__", counting_init)

    depth = 50
    node = {"name": "leaf-0", "children": []}
    for level in range(1, depth):
        node = {"name": f"leaf-{level}", "children": [node]}

    response = api_client.post(
        "/criteria/tree/import/", {"allows_multiple_primary_parents": False, "tree": [node]}, format="json"
    )

    assert response.status_code == 201
    # Linear bound (2x depth) rather than exact equality: proves no depth-driven blowup without
    # pinning the exact count of incidental serializer instantiations from field binding plumbing.
    assert instantiation_count <= depth * 2
