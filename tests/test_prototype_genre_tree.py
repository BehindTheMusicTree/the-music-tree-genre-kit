import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from tests.fixture_app.models import Criteria
from tests.fixture_app.viewset import GenreCriteriaViewSet
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


def test_load_example_tree_creates_criteria_from_fixture(api_client, user, criteria_type):
    response = api_client.post("/genre-criteria/tree/load-example/")

    assert response.status_code == 201
    names = set(Criteria.objects.filter(user=user).values_list("_name", flat=True))
    assert names == {"Electronic", "House", "Techno", "Rock"}


def test_load_example_tree_replaces_existing_criteria(api_client, user, criteria_type):
    stale = Criteria(user=user, type=criteria_type)
    stale._name = "stale"
    stale.save()

    response = api_client.post("/genre-criteria/tree/load-example/")

    assert response.status_code == 201
    assert not Criteria.objects.filter(user=user, _name="stale").exists()


def test_load_example_tree_missing_file_raises(api_client, criteria_type, settings, tmp_path):
    settings.DATA_DIR = tmp_path

    with pytest.raises(FileNotFoundError):
        api_client.post("/genre-criteria/tree/load-example/")


def test_load_example_tree_calls_on_loaded_hook(api_client, user, criteria_type, monkeypatch):
    calls = []

    monkeypatch.setattr(
        GenreCriteriaViewSet, "on_example_tree_loaded", lambda self, request: calls.append(request.user)
    )

    response = api_client.post("/genre-criteria/tree/load-example/")

    assert response.status_code == 201
    assert calls == [user]
