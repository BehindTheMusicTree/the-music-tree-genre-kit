"""SQL assignment publication for a staged population under its dataset write lock."""

from uuid import uuid4

from django.db import connection
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
                    WHERE n.dataset_id = %s ORDER BY a.track_id, n.identity, e.decision_id
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


def publish_staged_attributions(*, dataset, population, assignments):
    """Replace complete sets for population(track_id) from assignments(track_id,node_id,evidence_id).

    The caller holds the dataset write lock and owns both temporary staging tables.
    Populations stay in SQL, including empty sets and unchanged reviewed retries.
    """
    from the_music_tree_genre_kit.track.Track import Track

    from .storage import require_graph_write_context

    require_graph_write_context()
    quote = connection.ops.quote_name
    population, desired = quote(population), quote(assignments)
    attribution, link, evidence, node, state, track = (
        quote(model._meta.db_table)
        for model in (
            GenreGraphAttribution,
            GenreGraphAttributionEvidence,
            GenreGraphEvidence,
            GenreGraphNode,
            GenreGraphAssignmentState,
            Track,
        )
    )
    affected = quote(f"graph_assignment_changes_{uuid4().hex}")
    token = "gen_random_uuid()" if connection.vendor == "postgresql" else "lower(hex(randomblob(16)))"
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
        if connection.vendor == "postgresql":
            cursor.execute(
                f"DO $$ BEGIN PERFORM t.uuid FROM {track} t JOIN {population} p ON p.track_id = t.uuid ORDER BY t.uuid FOR UPDATE OF t; END $$"
            )
        cursor.execute(
            f"""CREATE TEMPORARY TABLE {affected} AS
            SELECT p.track_id FROM {population} p WHERE
                NOT EXISTS (SELECT 1 FROM {state} s WHERE s.dataset_id = %s AND s.track_id = p.track_id)
                OR EXISTS (
                    SELECT a.node_id, l.evidence_id FROM {attribution} a JOIN {node} n ON n.id = a.node_id
                    LEFT JOIN {link} l ON l.attribution_id = a.id WHERE n.dataset_id = %s AND a.track_id = p.track_id
                    EXCEPT SELECT d.node_id, d.evidence_id FROM {desired} d WHERE d.track_id = p.track_id
                ) OR EXISTS (
                    SELECT d.node_id, d.evidence_id FROM {desired} d WHERE d.track_id = p.track_id
                    EXCEPT SELECT a.node_id, l.evidence_id FROM {attribution} a JOIN {node} n ON n.id = a.node_id
                    JOIN {link} l ON l.attribution_id = a.id WHERE n.dataset_id = %s AND a.track_id = p.track_id
                )""",
            [dataset.pk, dataset.pk, dataset.pk],
        )
        cursor.execute(f"ANALYZE {affected}")
        cursor.execute(
            f"""INSERT INTO {state} (dataset_id, track_id, revision)
            SELECT %s, p.track_id, {token} FROM {affected} p WHERE NOT EXISTS (
                SELECT 1 FROM {state} s WHERE s.dataset_id = %s AND s.track_id = p.track_id
            )""",
            [dataset.pk, dataset.pk],
        )
        archive_population(cursor, dataset=dataset, affected=affected)
        selected = f"SELECT a.id FROM {attribution} a JOIN {node} n ON n.id = a.node_id JOIN {affected} p ON p.track_id = a.track_id WHERE n.dataset_id = %s"
        cursor.execute(f"DELETE FROM {link} WHERE attribution_id IN ({selected})", [dataset.pk])
        cursor.execute(f"DELETE FROM {attribution} WHERE id IN ({selected})", [dataset.pk])
        cursor.execute(f"""INSERT INTO {attribution} (track_id, node_id)
            SELECT DISTINCT d.track_id, d.node_id FROM {desired} d JOIN {affected} p ON p.track_id = d.track_id""")
        cursor.execute(f"""INSERT INTO {link} (attribution_id, evidence_id)
            SELECT DISTINCT a.id, d.evidence_id FROM {desired} d JOIN {affected} p ON p.track_id = d.track_id
            JOIN {attribution} a ON a.track_id = d.track_id AND a.node_id = d.node_id""")
        cursor.execute(
            f"UPDATE {state} SET revision = {token} WHERE dataset_id = %s AND track_id IN (SELECT track_id FROM {affected})",
            [dataset.pk],
        )
        archive_population(cursor, dataset=dataset, affected=affected)
        for model in (
            GenreGraphAssignmentState,
            GenreGraphAttribution,
            GenreGraphAttributionEvidence,
            GenreGraphAttributionRevision,
            GenreGraphEvidence,
        ):
            cursor.execute(f"ANALYZE {quote(model._meta.db_table)}")
        cursor.execute(f"DROP TABLE {affected}")
