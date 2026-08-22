import pytest
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException

from tests.fixture_app.models import Criteria
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks
from the_music_tree_genre_kit.serializer.field.criteria.CriteriaField import CriteriaField
from the_music_tree_genre_kit.serializer.field.criteria.CriteriaFieldInputType import CriteriaFieldInputType


class _CriteriaFieldSerializer(serializers.Serializer):
    def __init__(self, *args, input_types, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["criteria"] = CriteriaField(input_types=input_types, queryset=Criteria.objects.all())


def _build_serializer(user, input_types):
    request = Request(APIRequestFactory().post("/"))
    request.user = user
    return _CriteriaFieldSerializer(data={}, context={"request": request}, input_types=input_types)


@pytest.fixture
def user():
    return get_user_model().objects.create(username="fixture-user")


@pytest.fixture
def genre_type():
    return CriteriaType.objects.create(pk=int(CriteriaTypePks.GENRE), label="genre")


@pytest.mark.django_db
def test_to_internal_value_returns_none_for_blank_when_allowed(user):
    serializer = _build_serializer(user, [CriteriaFieldInputType.UUID, CriteriaFieldInputType.NAME])

    assert serializer.fields["criteria"].to_internal_value("") is None


@pytest.mark.django_db
def test_to_internal_value_fails_null_when_not_allowed(user):
    serializer = _build_serializer(user, [CriteriaFieldInputType.NAME])
    serializer.fields["criteria"]._allow_null = False

    with pytest.raises(AppValidationException):
        serializer.fields["criteria"].to_internal_value(None)


@pytest.mark.django_db
def test_to_internal_value_resolves_existing_uuid(user, genre_type):
    criteria = Criteria(user=user, type=genre_type)
    criteria._name = "House"
    criteria.save()

    serializer = _build_serializer(user, [CriteriaFieldInputType.UUID])

    resolved = serializer.fields["criteria"].to_internal_value(str(criteria.uuid))

    assert resolved.pk == criteria.pk


@pytest.mark.django_db
def test_to_internal_value_fails_when_uuid_looking_input_but_uuid_type_disabled(user):
    serializer = _build_serializer(user, [CriteriaFieldInputType.NAME])

    with pytest.raises(AppValidationException):
        serializer.fields["criteria"].to_internal_value("11111111-1111-1111-1111-111111111111")


@pytest.mark.django_db
def test_to_internal_value_get_or_creates_by_name(user, genre_type):
    serializer = _build_serializer(user, [CriteriaFieldInputType.NAME])
    serializer.fields["criteria"].get_queryset = lambda: Criteria.objects.filter(user=user, type=genre_type)

    resolved = serializer.fields["criteria"].to_internal_value("Techno")

    assert resolved.name == "Techno"
    assert Criteria.objects.filter(pk=resolved.pk).exists()


@pytest.mark.django_db
def test_to_internal_value_fails_when_no_input_type_matches(user):
    serializer = _build_serializer(user, [])

    with pytest.raises(AppValidationException):
        serializer.fields["criteria"].to_internal_value("not-a-uuid")


@pytest.mark.django_db
def test_to_representation_returns_uuid_string(user, genre_type):
    criteria = Criteria(user=user, type=genre_type)
    criteria._name = "House"
    criteria.save()

    serializer = _build_serializer(user, [CriteriaFieldInputType.UUID])

    assert serializer.fields["criteria"].to_representation(criteria) == str(criteria.uuid)
