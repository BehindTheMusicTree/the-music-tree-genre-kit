import uuid

import pytest
from django.contrib.auth import get_user_model

from tests.fixture_app.models import Genre
from the_music_tree_genre_kit.base import bulk_mti
from the_music_tree_genre_kit.base.bulk_mti import bulk_create_mti
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks


@pytest.fixture
def user(db):
    return get_user_model().objects.create(username="bulk-mti-user")


@pytest.fixture
def criteria_type(db):
    return CriteriaType.objects.create(pk=int(CriteriaTypePks.GENRE), label="genre")


def test_bulk_create_mti_inserts_all_rows_across_a_chunk_boundary(monkeypatch, user, criteria_type):
    # Force a small bound-parameter budget so a handful of instances still spans
    # multiple chunks, exercising the chunk-boundary path in _raw_insert_level
    # without needing thousands of rows.
    monkeypatch.setattr(bulk_mti, "POSTGRES_MAX_BOUND_PARAMS", 10)

    instances = []
    for i in range(7):
        genre = Genre(user=user, type=criteria_type)
        pk = uuid.uuid4()
        genre.uuid = pk
        genre.pk = pk
        genre._name = f"genre-{i}"
        genre.root = genre
        instances.append(genre)

    bulk_create_mti(instances, using="default")

    saved = Genre.objects.filter(pk__in=[instance.pk for instance in instances]).order_by("_name")
    assert [genre.name for genre in saved] == [f"genre-{i}" for i in range(7)]
    assert all(genre.root_id == genre.pk for genre in saved)
