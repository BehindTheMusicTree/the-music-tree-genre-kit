import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException
from the_music_tree_api_kit.exception.validation.FieldValidationErrorCode import FieldValidationErrorCode

from tests.fixture_app.models import Criteria
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks
from the_music_tree_genre_kit.serializer.field.foreign_key.DescendantAwareField import DescendantAwareField


class _DescendantAwareSerializer(serializers.Serializer):
    parent = DescendantAwareField(queryset=Criteria.objects.all(), allow_null=True, required=False)


def _build_serializer(user, instance=None):
    request = Request(APIRequestFactory().post("/"))
    request.user = user
    return _DescendantAwareSerializer(instance=instance, data={}, context={"request": request})


@pytest.fixture
def user():
    return get_user_model().objects.create(username="fixture-user")


@pytest.fixture
def genre_type():
    return CriteriaType.objects.create(pk=int(CriteriaTypePks.GENRE), label="genre")


def _make_criteria(user, genre_type, name, parent=None):
    criteria = Criteria(user=user, type=genre_type, parent=parent)
    criteria._name = name
    criteria.save()
    return criteria


@pytest.mark.django_db
def test_to_internal_value_returns_none_for_null(user, genre_type):
    serializer = _build_serializer(user)

    assert serializer.fields["parent"].to_internal_value(None) is None


@pytest.mark.django_db
def test_to_internal_value_raises_on_self_reference(user, genre_type):
    root = _make_criteria(user, genre_type, "root")
    serializer = _build_serializer(user, instance=root)

    with pytest.raises(AppValidationException) as exc_info:
        serializer.fields["parent"].to_internal_value(str(root.uuid))

    assert exc_info.value.field_validation_error_code == FieldValidationErrorCode.SELF_REFERENCE


@pytest.mark.django_db
def test_to_internal_value_raises_on_descendant_reference(user, genre_type):
    root = _make_criteria(user, genre_type, "root")
    child = _make_criteria(user, genre_type, "child", parent=root)
    serializer = _build_serializer(user, instance=root)

    with pytest.raises(AppValidationException) as exc_info:
        serializer.fields["parent"].to_internal_value(str(child.uuid))

    assert exc_info.value.field_validation_error_code == FieldValidationErrorCode.ANCESTOR_REFERENCE


@pytest.mark.django_db
def test_to_internal_value_allows_unrelated_reference(user, genre_type):
    root = _make_criteria(user, genre_type, "root")
    other = _make_criteria(user, genre_type, "other")
    serializer = _build_serializer(user, instance=root)

    resolved = serializer.fields["parent"].to_internal_value(str(other.uuid))

    assert resolved.pk == other.pk


@pytest.mark.django_db
def test_to_internal_value_raises_improperly_configured_when_instance_lacks_descendant_check(user, genre_type):
    other = _make_criteria(user, genre_type, "other")

    class _PlainInstance:
        uuid = "11111111-1111-1111-1111-111111111111"

    serializer = _build_serializer(user, instance=_PlainInstance())

    with pytest.raises(ImproperlyConfigured):
        serializer.fields["parent"].to_internal_value(str(other.uuid))


@pytest.mark.django_db
def test_to_internal_value_skips_descendant_check_when_no_instance(user, genre_type):
    other = _make_criteria(user, genre_type, "other")
    serializer = _build_serializer(user, instance=None)

    resolved = serializer.fields["parent"].to_internal_value(str(other.uuid))

    assert resolved.pk == other.pk
