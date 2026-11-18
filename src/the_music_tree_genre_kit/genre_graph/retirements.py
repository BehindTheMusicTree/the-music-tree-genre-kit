"""Set-based retirement publication, with complete before/after assignment archives."""

from uuid import uuid4

from django.db import connection

from .assignments import register_evidence
from .models import (
    GenreGraphAssignmentState,
    GenreGraphAttribution,
    GenreGraphAttributionEvidence,
    GenreGraphAttributionRevision,
    GenreGraphEvidence,
    GenreGraphNode,
)
from .publication import archive_population


def remap_retirements(*, dataset, decisions, nodes, previous_revision):
    if not decisions:
        return
    from the_music_tree_genre_kit.track.Track import Track

    registered = register_evidence(dataset, [decision["provenance"] for decision in decisions.values()])
    quote = connection.ops.quote_name
    attribution, link, track = (
        quote(model._meta.db_table) for model in (GenreGraphAttribution, GenreGraphAttributionEvidence, Track)
    )
    mapping = quote(f"graph_retirements_{uuid4().hex}")
    affected = quote(f"graph_retired_tracks_{uuid4().hex}")
    replacement = quote(f"graph_retired_replacements_{uuid4().hex}")
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE TEMPORARY TABLE {mapping} (node_id bigint PRIMARY KEY, target_id bigint, evidence_id bigint)"
        )
        cursor.executemany(
            f"INSERT INTO {mapping} VALUES (%s, %s, %s)",
            [
                (
                    nodes[identity].pk,
                    nodes[decision["target"]].pk if decision["target"] else None,
                    registered[decision["provenance"]["decisionId"]].pk,
                )
                for identity, decision in decisions.items()
            ],
        )
        cursor.execute(
            f"CREATE TEMPORARY TABLE {affected} AS SELECT DISTINCT a.track_id FROM {attribution} a JOIN {mapping} m ON m.node_id = a.node_id"
        )
        cursor.execute(
            f"CREATE UNIQUE INDEX ON {affected} (track_id)"
            if connection.vendor == "postgresql"
            else f"CREATE UNIQUE INDEX {quote('graph_retired_index_' + uuid4().hex)} ON {affected} (track_id)"
        )
        cursor.execute(f"ANALYZE {mapping}")
        cursor.execute(f"ANALYZE {affected}")
        if connection.vendor == "postgresql":
            # PERFORM discards rows in the backend instead of returning a catalogue to Python.
            cursor.execute(
                f"DO $$ BEGIN PERFORM t.uuid FROM {track} t JOIN {affected} c ON c.track_id = t.uuid ORDER BY t.uuid FOR UPDATE OF t; END $$"
            )
        published_revision = dataset.revision
        dataset.revision = previous_revision
        try:
            archive_population(cursor, dataset=dataset, affected=affected)
        finally:
            dataset.revision = published_revision
        # Preserve evidence before deleting sources so consumers can enforce one direct genre at every statement.
        cursor.execute(f"""CREATE TEMPORARY TABLE {replacement} AS
            SELECT a.track_id, m.target_id, l.evidence_id FROM {attribution} a
            JOIN {mapping} m ON m.node_id = a.node_id JOIN {link} l ON l.attribution_id = a.id
            WHERE m.target_id IS NOT NULL
            UNION SELECT a.track_id, m.target_id, m.evidence_id FROM {attribution} a
            JOIN {mapping} m ON m.node_id = a.node_id WHERE m.target_id IS NOT NULL""")
        cursor.execute(f"ANALYZE {replacement}")
        cursor.execute(
            f"DELETE FROM {link} WHERE attribution_id IN (SELECT a.id FROM {attribution} a JOIN {mapping} m ON m.node_id = a.node_id)"
        )
        cursor.execute(f"DELETE FROM {attribution} WHERE node_id IN (SELECT node_id FROM {mapping})")
        cursor.execute(
            f"""INSERT INTO {attribution} (track_id, node_id, dataset_id)
            SELECT DISTINCT source.track_id, source.target_id, %s FROM {replacement} source
            WHERE NOT EXISTS (
                SELECT 1 FROM {attribution} destination
                WHERE destination.track_id = source.track_id AND destination.node_id = source.target_id
            )""",
            [dataset.pk],
        )
        cursor.execute(f"""INSERT INTO {link} (attribution_id, evidence_id)
            SELECT destination.id, source.evidence_id FROM {replacement} source
            JOIN {attribution} destination ON destination.track_id = source.track_id AND destination.node_id = source.target_id
            WHERE NOT EXISTS (SELECT 1 FROM {link} existing
                WHERE existing.attribution_id = destination.id AND existing.evidence_id = source.evidence_id)""")
        archive_population(cursor, dataset=dataset, affected=affected)
        for model in (
            GenreGraphAttribution,
            GenreGraphAttributionEvidence,
            GenreGraphAssignmentState,
            GenreGraphAttributionRevision,
            GenreGraphEvidence,
        ):
            cursor.execute(f"ANALYZE {quote(model._meta.db_table)}")
        cursor.execute(f"DROP TABLE {replacement}")
        cursor.execute(f"DROP TABLE {affected}")
        cursor.execute(f"DROP TABLE {mapping}")
