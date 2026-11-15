import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from the_music_tree_genre_graph import GraphValidationError

from the_music_tree_genre_kit.genre_graph.storage import graph_read_snapshot


@pytest.mark.django_db(transaction=True)
def test_nested_snapshot_has_one_boundary_and_cleans_up_after_error():
    with CaptureQueriesContext(connection) as queries, graph_read_snapshot():
        try:
            with graph_read_snapshot():
                raise ValueError("consumer error")
        except ValueError:
            pass
        assert connection.graph_snapshot_depth == 1
    sql = [query["sql"] for query in queries]
    expected = ["BEGIN", "COMMIT"]
    if connection.vendor == "postgresql":
        expected.insert(1, "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    assert sql == expected
    assert connection.graph_snapshot_depth == 0


@pytest.mark.django_db(transaction=True)
def test_snapshot_error_rolls_back_and_restores_state():
    with pytest.raises(ValueError, match="consumer error"), graph_read_snapshot():
        raise ValueError("consumer error")
    assert connection.graph_snapshot_depth == 0
    assert not connection.in_atomic_block


@pytest.mark.django_db(transaction=True)
def test_snapshot_rejects_unrelated_transaction():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL")
    with transaction.atomic(), pytest.raises(GraphValidationError, match="outermost"), graph_read_snapshot():
        pytest.fail("snapshot accepted an unrelated transaction")
