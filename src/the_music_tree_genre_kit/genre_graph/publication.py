"""SQL assignment publication for a staged population under its dataset write lock."""

from contextlib import contextmanager, nullcontext
from uuid import uuid4

from django.db import DatabaseError, connection
from the_music_tree_genre_graph import GraphValidationError

from .models import (
    GenreGraphAssignmentState,
    GenreGraphAttribution,
    GenreGraphAttributionEvidence,
    GenreGraphAttributionRevision,
    GenreGraphEvidence,
    GenreGraphNode,
)


def archive_population(cursor, *, dataset, affected):
    """Archive SQL populations; only graph-sized decisions ever enter Python."""
    quote = connection.ops.quote_name
    attribution, link, evidence, node, state, history = (
        quote(model._meta.db_table)
        for model in (
            GenreGraphAttribution,
            GenreGraphAttributionEvidence,
            GenreGraphEvidence,
            GenreGraphNode,
            GenreGraphAssignmentState,
            GenreGraphAttributionRevision,
        )
    )
    if connection.vendor == "postgresql":
        evidence_json = "jsonb_build_object('decisionId', e.decision_id, 'source', e.source, 'rationale', e.rationale)"
        evidence_set = "jsonb_agg(evidence ORDER BY decision_id)"
        assignment_set = "jsonb_object_agg(identity, evidence)"
        empty = "'{}'::jsonb"
        timestamp = "CURRENT_TIMESTAMP"
    else:
        evidence_json = "json_object('decisionId', e.decision_id, 'source', e.source, 'rationale', e.rationale)"
        evidence_set = "json_group_array(json(evidence))"
        assignment_set = "json_group_object(identity, json(evidence))"
        empty = "'{}'"
        timestamp = "strftime('%Y-%m-%d %H:%M:%f', 'now')"
    # The inner grouping captures complete assignments, including unaffected destinations.
    cursor.execute(
        f"""INSERT INTO {history} (revision, dataset_id, track_id, graph_revision, attributions, created_at)
        SELECT s.revision, s.dataset_id, s.track_id, %s, COALESCE(population.attributions, {empty}), {timestamp}
        FROM {state} s JOIN {affected} changed ON changed.track_id = s.track_id
        LEFT JOIN (
            SELECT track_id, {assignment_set} AS attributions FROM (
                SELECT track_id, identity, {evidence_set} AS evidence FROM (
                    SELECT a.track_id, n.identity, e.decision_id, {evidence_json} AS evidence
                    FROM {attribution} a JOIN {node} n ON n.id = a.node_id
                    JOIN {affected} changed ON changed.track_id = a.track_id
                    JOIN {link} l ON l.attribution_id = a.id JOIN {evidence} e ON e.id = l.evidence_id
                    WHERE a.dataset_id = %s ORDER BY a.track_id, n.identity, e.decision_id
                ) ordered_evidence GROUP BY track_id, identity
            ) sets GROUP BY track_id
        ) population ON population.track_id = s.track_id
        WHERE s.dataset_id = %s AND NOT EXISTS (SELECT 1 FROM {history} h WHERE h.revision = s.revision)""",
        [
            GenreGraphAttributionRevision._meta.get_field("graph_revision").get_db_prep_value(
                dataset.revision, connection
            ),
            dataset.pk,
            dataset.pk,
        ],
    )


BYPASS_SETTING = "the_music_tree_genre_kit.staged_publication"


@contextmanager
def _staged_publication_bypass(cursor):
    """Let the row-level guards of migration 0025 stand down; the set-wise checks of this module replace them."""
    if connection.vendor != "postgresql":
        yield
        return
    cursor.execute("SELECT set_config(%s, 'on', true)", [BYPASS_SETTING])
    try:
        yield
    finally:
        try:
            cursor.execute("SELECT set_config(%s, 'off', true)", [BYPASS_SETTING])
        except DatabaseError:
            # The transaction is already aborted; its rollback restores the transaction-local setting.
            pass


def publish_staged_attributions(*, dataset, population, assignments, chunk_size=None, on_step=None):
    """Replace complete sets for population(track_id) from assignments(track_id,node_id,evidence_id).

    The caller holds the dataset write lock and owns both temporary staging tables.
    Populations stay in SQL. Only tracks whose set changes are touched: tracks without a state and without desired
    assignments get neither a state nor a history. Bulk writes run in chunks of `chunk_size` affected tracks
    (all at once when None), checking deferred constraints after each chunk. `on_step(name)` returns a context
    manager wrapped around each phase (affected, lock, archive_before, write, state, archive_after, analyze).
    """
    from the_music_tree_genre_kit.track.Track import Track

    from .models import GenreGraphDataset
    from .storage import require_graph_write_context

    require_graph_write_context()
    if chunk_size is not None and chunk_size < 1:
        raise ValueError("chunk_size must be positive")

    def step(name):
        return on_step(name) if on_step else nullcontext()

    postgresql = connection.vendor == "postgresql"
    quote = connection.ops.quote_name
    population, desired = quote(population), quote(assignments)
    attribution, link, evidence, node, state, track, dataset_table = (
        quote(model._meta.db_table)
        for model in (
            GenreGraphAttribution,
            GenreGraphAttributionEvidence,
            GenreGraphEvidence,
            GenreGraphNode,
            GenreGraphAssignmentState,
            Track,
            GenreGraphDataset,
        )
    )
    suffix = uuid4().hex
    affected = quote(f"graph_assignment_changes_{suffix}")
    token = "gen_random_uuid()" if postgresql else "lower(hex(randomblob(16)))"
    has_state = f"EXISTS (SELECT 1 FROM {state} s WHERE s.dataset_id = %s AND s.track_id = {{track}})"
    with connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT EXISTS (
            SELECT 1 FROM {desired} d LEFT JOIN {population} p ON p.track_id = d.track_id
            LEFT JOIN {node} n ON n.id = d.node_id LEFT JOIN {evidence} e ON e.id = d.evidence_id
            WHERE p.track_id IS NULL OR n.id IS NULL OR n.dataset_id <> %s OR NOT n.is_active
                OR e.id IS NULL OR e.dataset_id <> %s
            UNION ALL SELECT 1 FROM {population} p LEFT JOIN {track} t ON t.uuid = p.track_id
            WHERE t.uuid IS NULL OR t.user_id IS NOT NULL
        )""",
            [dataset.pk, dataset.pk],
        )
        if cursor.fetchone()[0]:
            raise GraphValidationError(
                "Staged assignments require ownerless tracks and active dataset identities/evidence"
            )
        cursor.execute(
            f"""SELECT EXISTS (
            SELECT 1 FROM {desired} d JOIN {population} p ON p.track_id = d.track_id
            GROUP BY d.track_id HAVING count(DISTINCT d.node_id) > 1)"""
        )
        if cursor.fetchone()[0]:
            raise GraphValidationError("A track holds at most one node per dataset in staged assignments")
        with step("affected"):
            # Anti/semi-joins on both sides of the difference between the stored and the desired sets;
            # a stored attribution without evidence never matches, so it always counts as a difference.
            current = (
                f"SELECT a.track_id, a.node_id, l.evidence_id FROM {attribution} a "
                f"JOIN {population} p ON p.track_id = a.track_id "
                f"LEFT JOIN {link} l ON l.attribution_id = a.id WHERE a.dataset_id = %s"
            )
            cursor.execute(
                f"""CREATE TEMPORARY TABLE {affected} AS
                SELECT row_number() OVER (ORDER BY track_id) AS n, track_id FROM (
                    SELECT p.track_id FROM {population} p
                    WHERE NOT {has_state.format(track="p.track_id")}
                        AND EXISTS (SELECT 1 FROM {desired} d WHERE d.track_id = p.track_id)
                    UNION
                    SELECT c.track_id FROM ({current}) c
                    WHERE {has_state.format(track="c.track_id")} AND NOT EXISTS (
                        SELECT 1 FROM {desired} d
                        WHERE d.track_id = c.track_id AND d.node_id = c.node_id AND d.evidence_id = c.evidence_id)
                    UNION
                    SELECT d.track_id FROM {desired} d
                    WHERE {has_state.format(track="d.track_id")} AND NOT EXISTS (
                        SELECT 1 FROM {attribution} a JOIN {link} l ON l.attribution_id = a.id
                        WHERE a.dataset_id = %s AND a.track_id = d.track_id AND a.node_id = d.node_id
                            AND l.evidence_id = d.evidence_id)
                ) changed""",
                [dataset.pk] * 5,
            )
            cursor.execute(f"CREATE UNIQUE INDEX {quote(f'graph_changes_n_{suffix}')} ON {affected} (n)")
            cursor.execute(f"CREATE UNIQUE INDEX {quote(f'graph_changes_track_{suffix}')} ON {affected} (track_id)")
            cursor.execute(f"ANALYZE {affected}")
            cursor.execute(f"SELECT count(*) FROM {affected}")
            total = cursor.fetchone()[0]
        with step("lock"):
            if postgresql:
                cursor.execute(f"SELECT 1 FROM {dataset_table} WHERE key = %s FOR UPDATE", [dataset.pk])
                cursor.execute(
                    f"DO $$ BEGIN PERFORM t.uuid FROM {track} t JOIN {affected} a ON a.track_id = t.uuid "
                    f"ORDER BY t.uuid FOR UPDATE OF t; END $$"
                )
            cursor.execute(
                f"SELECT EXISTS (SELECT 1 FROM {affected} a JOIN {track} t ON t.uuid = a.track_id "
                f"WHERE t.user_id IS NOT NULL)"
            )
            if cursor.fetchone()[0]:
                raise GraphValidationError("Staged assignments require ownerless tracks")
        with step("archive_before"):
            # Only tracks that already hold a state have something to archive.
            archive_population(cursor, dataset=dataset, affected=affected)
        size = chunk_size or max(total, 1)
        chunks = [(low, low + size - 1) for low in range(1, total + 1, size)]
        restore_immediate = []
        if postgresql:
            cursor.execute("SELECT conname FROM pg_constraint WHERE condeferrable AND NOT condeferred")
            restore_immediate = sorted({row[0] for row in cursor.fetchall()})

        def check_constraints():
            if not postgresql:
                return
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("SET CONSTRAINTS ALL DEFERRED")
            if restore_immediate:
                cursor.execute("SET CONSTRAINTS " + ", ".join(quote(name) for name in restore_immediate) + " IMMEDIATE")

        in_chunk = f"{{track}} IN (SELECT track_id FROM {affected} WHERE n BETWEEN %s AND %s)"
        with _staged_publication_bypass(cursor):
            with step("write"):
                for low, high in chunks:
                    selected = (
                        f"SELECT a.id FROM {attribution} a JOIN {affected} p ON p.track_id = a.track_id "
                        f"WHERE a.dataset_id = %s AND p.n BETWEEN %s AND %s"
                    )
                    bounds = [dataset.pk, low, high]
                    cursor.execute(f"DELETE FROM {link} WHERE attribution_id IN ({selected})", bounds)
                    cursor.execute(f"DELETE FROM {attribution} WHERE id IN ({selected})", bounds)
                    cursor.execute(
                        f"""INSERT INTO {attribution} (track_id, node_id, dataset_id)
                        SELECT DISTINCT d.track_id, d.node_id, %s FROM {desired} d JOIN {affected} p
                        ON p.track_id = d.track_id WHERE p.n BETWEEN %s AND %s""",
                        bounds,
                    )
                    cursor.execute(
                        f"""INSERT INTO {link} (attribution_id, evidence_id)
                        SELECT DISTINCT a.id, d.evidence_id FROM {desired} d JOIN {affected} p
                        ON p.track_id = d.track_id
                        JOIN {attribution} a ON a.track_id = d.track_id AND a.node_id = d.node_id
                        WHERE a.dataset_id = %s AND p.n BETWEEN %s AND %s""",
                        bounds,
                    )
                    check_constraints()
            with step("state"):
                for low, high in chunks:
                    cursor.execute(
                        f"UPDATE {state} SET revision = {token} WHERE dataset_id = %s AND "
                        + in_chunk.format(track="track_id"),
                        [dataset.pk, low, high],
                    )
                    # New tracks receive their final token directly: nothing was archived for them before.
                    cursor.execute(
                        f"""INSERT INTO {state} (dataset_id, track_id, revision)
                        SELECT %s, p.track_id, {token} FROM {affected} p WHERE p.n BETWEEN %s AND %s
                        AND NOT EXISTS (SELECT 1 FROM {state} s WHERE s.dataset_id = %s AND s.track_id = p.track_id)
                        AND EXISTS (SELECT 1 FROM {desired} d WHERE d.track_id = p.track_id)""",
                        [dataset.pk, low, high, dataset.pk],
                    )
                    check_constraints()
        with step("archive_after"):
            archive_population(cursor, dataset=dataset, affected=affected)
        with step("analyze"):
            for model in (
                GenreGraphAssignmentState,
                GenreGraphAttribution,
                GenreGraphAttributionEvidence,
                GenreGraphAttributionRevision,
                GenreGraphEvidence,
            ):
                cursor.execute(f"ANALYZE {quote(model._meta.db_table)}")
        cursor.execute(f"DROP TABLE {affected}")
