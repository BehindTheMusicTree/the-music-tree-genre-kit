"""Graph-sized staging and dataset-owned SQL diff, never catalogue enumeration."""

from tempfile import TemporaryFile
from uuid import uuid4

from django.db import connection
from the_music_tree_genre_graph import GraphValidationError

from .models import GenreGraphAccess, GenreGraphNode, GraphScope


def replace_access(dataset, graph, nodes):
    if connection.vendor not in {"postgresql", "sqlite"}:
        raise GraphValidationError("Reference graphs require PostgreSQL or SQLite")
    quote = connection.ops.quote_name
    table = quote(GenreGraphAccess._meta.db_table)
    stage = quote(f"graph_access_stage_{uuid4().hex}")

    def desired():
        for identity, node in nodes.items():
            for scope in GraphScope:
                for descendant in graph.selected_nodes(identity, scope=scope.value):
                    yield node.pk, scope.value, nodes[descendant].pk

    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE TEMPORARY TABLE {stage} (ancestor_id bigint, scope varchar(16), descendant_id bigint, "
            "PRIMARY KEY (ancestor_id, scope, descendant_id))"
        )
        if connection.vendor == "postgresql":
            from django.db.backends.postgresql.psycopg_any import is_psycopg3

            copy_sql = f"COPY {stage} (ancestor_id, scope, descendant_id) FROM STDIN"
            if is_psycopg3:
                with cursor.copy(copy_sql) as copy:
                    for row in desired():
                        copy.write_row(row)
            else:
                with TemporaryFile(mode="w+", encoding="utf-8") as rows:
                    rows.writelines(f"{ancestor}\t{scope}\t{descendant}\n" for ancestor, scope, descendant in desired())
                    rows.seek(0)
                    cursor.copy_expert(copy_sql, rows)
        else:
            cursor.executemany(f"INSERT INTO {stage} VALUES (%s, %s, %s)", desired())
        cursor.execute(f"ANALYZE {stage}")
        cursor.execute(
            f"DELETE FROM {table} WHERE dataset_id = %s AND NOT EXISTS (SELECT 1 FROM {stage} s "
            f"WHERE s.ancestor_id = {table}.ancestor_id AND s.scope = {table}.scope "
            f"AND s.descendant_id = {table}.descendant_id)",
            [dataset.pk],
        )
        deleted = cursor.rowcount
        cursor.execute(
            f"INSERT INTO {table} (dataset_id, ancestor_id, scope, descendant_id) "
            f"SELECT %s, s.ancestor_id, s.scope, s.descendant_id FROM {stage} s WHERE TRUE "
            "ON CONFLICT (ancestor_id, scope, descendant_id) DO NOTHING",
            [dataset.pk],
        )
        inserted = cursor.rowcount
        if deleted or inserted:
            cursor.execute(f"ANALYZE {table}")
        cursor.execute(f"DROP TABLE {stage}")


def analyze_nodes():
    with connection.cursor() as cursor:
        cursor.execute(f"ANALYZE {connection.ops.quote_name(GenreGraphNode._meta.db_table)}")
