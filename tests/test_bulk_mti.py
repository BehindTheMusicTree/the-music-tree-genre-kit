import math
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test.utils import CaptureQueriesContext

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


def _genres(user, criteria_type, count):
    instances = []
    for i in range(count):
        genre = Genre(user=user, type=criteria_type)
        pk = uuid.uuid4()
        genre.uuid = pk
        genre.pk = pk
        genre._name = f"genre-{i}"
        genre.root = genre
        instances.append(genre)
    return instances


def _expected_insert_count(row_count, budget):
    return sum(
        math.ceil(row_count / max(1, budget // len(level._meta.local_fields)))
        for level in bulk_mti._base_first_concrete_chain(Genre)
    )


def _run_counting_inserts(instances):
    with CaptureQueriesContext(connections["default"]) as ctx:
        bulk_create_mti(instances, using="default")
    return sum(query["sql"].startswith("INSERT") for query in ctx.captured_queries)


def test_bulk_create_mti_inserts_all_rows_across_a_chunk_boundary(monkeypatch, user, criteria_type):
    # Force a small bound-parameter budget so a handful of instances still spans
    # multiple chunks, exercising the chunk-boundary path in _raw_insert_level
    # without needing thousands of rows. max_query_params=None mimics Postgres.
    monkeypatch.setattr(connections["default"].features, "max_query_params", None)
    monkeypatch.setattr(bulk_mti, "POSTGRES_MAX_BOUND_PARAMS", 10)
    instances = _genres(user, criteria_type, 7)

    assert _run_counting_inserts(instances) == _expected_insert_count(7, 10)

    saved = Genre.objects.filter(pk__in=[instance.pk for instance in instances]).order_by("_name")
    assert [genre.name for genre in saved] == [f"genre-{i}" for i in range(7)]
    assert all(genre.root_id == genre.pk for genre in saved)


def test_bulk_create_mti_chunks_by_backend_max_query_params(monkeypatch, user, criteria_type):
    monkeypatch.setattr(connections["default"].features, "max_query_params", 10)
    instances = _genres(user, criteria_type, 7)

    assert _run_counting_inserts(instances) == _expected_insert_count(7, 10)
    assert Genre.objects.filter(pk__in=[instance.pk for instance in instances]).count() == 7
