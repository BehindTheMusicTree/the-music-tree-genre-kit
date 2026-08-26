import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from tests.fixture_app.models import Criteria
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType


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

    response = api_client.get("/criteria/tree/")

    assert response.status_code == 200
    assert response.data == [
        {"name": "root", "children": [{"name": "child", "children": [], "side": None}], "side": None}
    ]


def test_tree_excludes_other_users_criteria(api_client, user, criteria_type):
    other_user = get_user_model().objects.create(username="other-user")
    other_root = Criteria(user=other_user, type=criteria_type)
    other_root._name = "other-root"
    other_root.save()

    response = api_client.get("/criteria/tree/")

    assert response.status_code == 200
    assert response.data == []


def test_import_tree_creates_criteria(api_client, criteria_type):
    payload = {"tree": [{"name": "root", "children": [{"name": "child", "children": []}]}]}

    response = api_client.post("/criteria/tree/import/", payload, format="json")

    assert response.status_code == 201
    names = {result["name"] for result in response.data["results"]}
    assert names == {"root", "child"}


def test_import_tree_replaces_existing_criteria(api_client, user, criteria_type):
    stale = Criteria(user=user, type=criteria_type)
    stale._name = "stale"
    stale.save()

    payload = {"tree": [{"name": "fresh", "children": []}]}

    response = api_client.post("/criteria/tree/import/", payload, format="json")

    assert response.status_code == 201
    names = {result["name"] for result in response.data["results"]}
    assert names == {"fresh"}
    assert not Criteria.objects.filter(user=user).filter(_name="stale").exists()


def test_import_tree_rejects_empty_tree(api_client, criteria_type):
    response = api_client.post("/criteria/tree/import/", {"tree": []}, format="json")

    assert response.status_code == 400
