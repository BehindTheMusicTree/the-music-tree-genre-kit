"""Enforce active references, permanent evidence/audit, and direct-SQL CAS invalidation."""

from django.db import migrations

P = "the_music_tree_genre_kit_"
A = P + "genregraphattribution"
N = P + "genregraphnode"
D = P + "genregraphdataset"
E = P + "genregraphevidence"
L = P + "genregraphattributionevidence"
S = P + "genregraphassignmentstate"
T = P + "track"


def install(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor not in {"postgresql", "sqlite"}:
        raise RuntimeError("Reference graphs require PostgreSQL or SQLite")
    guards = {
        "graph_active_attribution": (A, f"NOT EXISTS (SELECT 1 FROM {N} WHERE id = NEW.node_id AND is_active)"),
        "graph_retire_node": (N, f"NOT NEW.is_active AND EXISTS (SELECT 1 FROM {A} WHERE node_id = NEW.id)"),
        "graph_evidence_dataset": (
            L,
            f"""NOT EXISTS (SELECT 1 FROM {A} a JOIN {N} n ON n.id = a.node_id
            JOIN {E} e ON e.dataset_id = n.dataset_id WHERE a.id = NEW.attribution_id AND e.id = NEW.evidence_id)""",
        ),
    }
    for name, (table, condition) in guards.items():
        operations = ("update",) if table == N else ("insert", "update")
        for operation in operations:
            trigger = name + "_" + operation
            if vendor == "postgresql":
                # Active checks must run after the publication lock, before the owner trigger locks a track.
                lock = ""
                if table == A:
                    node_ids = "NEW.node_id" if operation == "insert" else "OLD.node_id, NEW.node_id"
                    lock = f"PERFORM d.key FROM {D} d WHERE d.key IN (SELECT dataset_id FROM {N} WHERE id IN ({node_ids})) ORDER BY d.key FOR UPDATE;"
                elif table == N:
                    lock = f"PERFORM key FROM {D} WHERE key = NEW.dataset_id FOR UPDATE;"
                elif table == L:
                    evidence_ids = "NEW.evidence_id" if operation == "insert" else "OLD.evidence_id, NEW.evidence_id"
                    lock = f"PERFORM key FROM {D} WHERE key IN (SELECT dataset_id FROM {E} WHERE id IN ({evidence_ids})) ORDER BY key FOR UPDATE;"
                schema_editor.execute(f"""CREATE FUNCTION {trigger}() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN {lock} IF {condition} THEN
                        RAISE EXCEPTION 'Invalid active graph reference or evidence dataset' USING ERRCODE = '23514';
                    END IF; RETURN NEW; END $$""")
                schema_editor.execute(f"""CREATE TRIGGER {trigger} BEFORE {operation.upper()} ON {table}
                    FOR EACH ROW EXECUTE FUNCTION {trigger}()""")
            else:
                schema_editor.execute(f"""CREATE TRIGGER {trigger} BEFORE {operation.upper()} ON {table}
                    WHEN {condition} BEGIN SELECT RAISE(ABORT, 'Invalid active graph reference or evidence dataset'); END""")
    # Moving an assignment with evidence would detach that evidence from its dataset.
    condition = f"""EXISTS (SELECT 1 FROM {L} l JOIN {E} e ON e.id = l.evidence_id
        JOIN {N} n ON n.id = NEW.node_id WHERE l.attribution_id = OLD.id AND e.dataset_id <> n.dataset_id)"""
    if vendor == "postgresql":
        schema_editor.execute(f"""CREATE FUNCTION graph_assignment_dataset() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF {condition} THEN RAISE EXCEPTION 'Evidence dataset cannot change' USING ERRCODE = '23514';
            END IF; RETURN NEW; END $$""")
        schema_editor.execute(f"""CREATE TRIGGER graph_assignment_dataset BEFORE UPDATE ON {A}
            FOR EACH ROW EXECUTE FUNCTION graph_assignment_dataset()""")
    else:
        schema_editor.execute(f"""CREATE TRIGGER graph_assignment_dataset BEFORE UPDATE ON {A} WHEN {condition}
            BEGIN SELECT RAISE(ABORT, 'Evidence dataset cannot change'); END""")
    for suffix in ("genregraphevidence", "genregraphrevision", "genregraphattributionrevision", "genregraphnode"):
        table = P + suffix
        for operation in ("delete",) if suffix == "genregraphnode" else ("update", "delete"):
            name = suffix + "_immutable_" + operation
            if vendor == "postgresql":
                schema_editor.execute(f"""CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN RAISE EXCEPTION 'Graph evidence and audit are immutable' USING ERRCODE = '23514'; END $$""")
                schema_editor.execute(f"""CREATE TRIGGER {name} BEFORE {operation.upper()} ON {table}
                    FOR EACH ROW EXECUTE FUNCTION {name}()""")
            else:
                schema_editor.execute(f"""CREATE TRIGGER {name} BEFORE {operation.upper()} ON {table}
                    BEGIN SELECT RAISE(ABORT, 'Graph evidence and audit are immutable'); END""")
    for table, prefix in ((A, "graph_assignment_cas"), (L, "graph_evidence_cas")):
        for operation in ("insert", "update", "delete"):
            name = prefix + "_" + operation
            refs = (
                ["new_rows"]
                if operation == "insert"
                else ["old_rows"]
                if operation == "delete"
                else ["old_rows", "new_rows"]
            )
            if vendor == "postgresql":
                sets = " UNION ".join(
                    f"SELECT n.dataset_id, r.track_id FROM {ref} r JOIN {N} n ON n.id = r.node_id"
                    if table == A
                    else f"SELECT n.dataset_id, a.track_id FROM {ref} r JOIN {A} a ON a.id = r.attribution_id JOIN {N} n ON n.id = a.node_id"
                    for ref in refs
                )
                referencing = " ".join(
                    "NEW TABLE AS new_rows" if ref == "new_rows" else "OLD TABLE AS old_rows" for ref in refs
                )
                schema_editor.execute(f"""CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
                    INSERT INTO {S} (dataset_id, track_id, revision)
                    SELECT affected.dataset_id, affected.track_id, gen_random_uuid() FROM (SELECT DISTINCT dataset_id, track_id FROM ({sets}) pairs) affected
                    JOIN {T} t ON t.uuid = affected.track_id
                    WHERE {"true" if operation != "delete" else f"EXISTS (SELECT 1 FROM {S} s WHERE s.dataset_id = affected.dataset_id AND s.track_id = affected.track_id)"}
                    ON CONFLICT (dataset_id, track_id) DO UPDATE SET revision = EXCLUDED.revision;
                    UPDATE {D} SET membership_revision = gen_random_uuid()
                    WHERE key IN (SELECT dataset_id FROM ({sets}) affected);
                    RETURN NULL; END $$""")
                schema_editor.execute(f"""CREATE TRIGGER {name} AFTER {operation.upper()} ON {table}
                    REFERENCING {referencing} FOR EACH STATEMENT EXECUTE FUNCTION {name}()""")
            else:
                refs = ["NEW"] if operation == "insert" else ["OLD"] if operation == "delete" else ["OLD", "NEW"]
                sets = " UNION ".join(
                    f"SELECT n.dataset_id, {ref}.track_id AS track_id FROM {N} n WHERE n.id = {ref}.node_id"
                    if table == A
                    else f"SELECT n.dataset_id, a.track_id FROM {A} a JOIN {N} n ON n.id = a.node_id WHERE a.id = {ref}.attribution_id"
                    for ref in refs
                )
                schema_editor.execute(f"""CREATE TRIGGER {name} AFTER {operation.upper()} ON {table} BEGIN
                    INSERT INTO {S} (dataset_id, track_id, revision)
                    SELECT affected.dataset_id, affected.track_id, lower(hex(randomblob(16)))
                    FROM (SELECT DISTINCT dataset_id, track_id FROM ({sets}) pairs) affected JOIN {T} t ON t.uuid = affected.track_id WHERE {"true" if operation != "delete" else f"EXISTS (SELECT 1 FROM {S} s WHERE s.dataset_id = affected.dataset_id AND s.track_id = affected.track_id)"}
                    ON CONFLICT (dataset_id, track_id) DO UPDATE SET revision = excluded.revision;
                    UPDATE {D} SET membership_revision = lower(hex(randomblob(16)))
                    WHERE key IN (SELECT dataset_id FROM ({sets}) affected);
                    END""")


def uninstall(apps, schema_editor):
    pg = schema_editor.connection.vendor == "postgresql"
    for name, table, operations in (
        ("graph_active_attribution", A, ("insert", "update")),
        ("graph_retire_node", N, ("update",)),
        ("graph_evidence_dataset", L, ("insert", "update")),
        ("graph_assignment_cas", A, ("insert", "update", "delete")),
        ("graph_evidence_cas", L, ("insert", "update", "delete")),
        *(
            (suffix + "_immutable", P + suffix, ("update", "delete"))
            for suffix in ("genregraphevidence", "genregraphrevision", "genregraphattributionrevision")
        ),
        ("genregraphnode_immutable", N, ("delete",)),
        ("graph_assignment_dataset", A, ("",)),
    ):
        for operation in operations:
            trigger = name + ("_" + operation if operation else "")
            schema_editor.execute(f"DROP TRIGGER {trigger}" + (f" ON {table}" if pg else ""))
            if pg:
                schema_editor.execute(f"DROP FUNCTION {trigger}()")


class Migration(migrations.Migration):
    dependencies = [("the_music_tree_genre_kit", "0020_immutable_assignment_evidence")]
    operations = [migrations.RunPython(install, uninstall)]
