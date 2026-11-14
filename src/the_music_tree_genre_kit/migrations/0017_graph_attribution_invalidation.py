"""Invalidate membership caches even for bulk writes and deletion cascades."""

from django.db import migrations


PREFIX = "the_music_tree_genre_kit_"
DATASET = f"{PREFIX}genregraphdataset"
NODE = f"{PREFIX}genregraphnode"
ATTRIBUTION = f"{PREFIX}genregraphattribution"
TRACK = f"{PREFIX}track"


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            f"""CREATE FUNCTION graph_attribution_owner() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE track_is_private boolean;
            BEGIN
                -- Lock even an ownerless row so an ownership transfer must wait.
                SELECT user_id IS NOT NULL INTO track_is_private FROM {TRACK}
                WHERE uuid = NEW.track_id FOR UPDATE;
                IF track_is_private THEN
                    RAISE EXCEPTION 'Reference graph attributions require an ownerless track'
                        USING ERRCODE = 'check_violation';
                END IF;
                RETURN NEW;
            END; $$"""
        )
        schema_editor.execute(
            f"""CREATE TRIGGER graph_attribution_owner BEFORE INSERT OR UPDATE ON {ATTRIBUTION}
            FOR EACH ROW EXECUTE FUNCTION graph_attribution_owner()"""
        )
        schema_editor.execute(
            f"""CREATE FUNCTION graph_track_owner() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.user_id IS NOT NULL AND EXISTS (
                    SELECT 1 FROM {ATTRIBUTION} WHERE track_id = NEW.uuid
                ) THEN
                    RAISE EXCEPTION 'Reference graph attributions require an ownerless track'
                        USING ERRCODE = 'check_violation';
                END IF;
                RETURN NEW;
            END; $$"""
        )
        schema_editor.execute(
            f"""CREATE TRIGGER graph_track_owner BEFORE UPDATE OF user_id ON {TRACK}
            FOR EACH ROW EXECUTE FUNCTION graph_track_owner()"""
        )
        for operation, references, rows in (
            ("insert", "NEW TABLE AS new_rows", "SELECT node_id FROM new_rows"),
            ("delete", "OLD TABLE AS old_rows", "SELECT node_id FROM old_rows"),
            (
                "update",
                "OLD TABLE AS old_rows NEW TABLE AS new_rows",
                "SELECT node_id FROM old_rows UNION SELECT node_id FROM new_rows",
            ),
        ):
            function = f"graph_attribution_{operation}"
            schema_editor.execute(
                f"""CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    UPDATE {DATASET} SET membership_revision = gen_random_uuid()
                    WHERE key IN (
                        SELECT DISTINCT dataset_id FROM {NODE}
                        WHERE id IN ({rows})
                    );
                    RETURN NULL;
                END; $$"""
            )
            # Transition tables invalidate once per affected dataset, not once
            # per track during a full catalogue import.
            schema_editor.execute(
                f"""CREATE TRIGGER {function} AFTER {operation.upper()} ON {ATTRIBUTION}
                REFERENCING {references} FOR EACH STATEMENT EXECUTE FUNCTION {function}()"""
            )
    elif schema_editor.connection.vendor == "sqlite":
        for operation in ("insert", "update"):
            schema_editor.execute(
                f"""CREATE TRIGGER graph_attribution_owner_{operation}
                BEFORE {operation.upper()} ON {ATTRIBUTION}
                WHEN EXISTS (SELECT 1 FROM {TRACK} WHERE uuid = NEW.track_id AND user_id IS NOT NULL)
                BEGIN SELECT RAISE(ABORT, 'Reference graph attributions require an ownerless track'); END"""
            )
        schema_editor.execute(
            f"""CREATE TRIGGER graph_track_owner BEFORE UPDATE OF user_id ON {TRACK}
            WHEN NEW.user_id IS NOT NULL AND EXISTS (SELECT 1 FROM {ATTRIBUTION} WHERE track_id = NEW.uuid)
            BEGIN SELECT RAISE(ABORT, 'Reference graph attributions require an ownerless track'); END"""
        )
        for operation, references in (
            ("insert", "NEW.node_id"),
            ("delete", "OLD.node_id"),
            ("update", "OLD.node_id, NEW.node_id"),
        ):
            schema_editor.execute(
                f"""CREATE TRIGGER graph_attribution_{operation}
                AFTER {operation.upper()} ON {ATTRIBUTION} BEGIN
                    UPDATE {DATASET} SET membership_revision = lower(hex(randomblob(16)))
                    WHERE key IN (SELECT dataset_id FROM {NODE} WHERE id IN ({references}));
                END"""
            )
    else:
        raise RuntimeError("Semantic graph storage requires PostgreSQL or SQLite")


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f"DROP TRIGGER graph_attribution_owner ON {ATTRIBUTION}")
        schema_editor.execute("DROP FUNCTION graph_attribution_owner()")
        schema_editor.execute(f"DROP TRIGGER graph_track_owner ON {TRACK}")
        schema_editor.execute("DROP FUNCTION graph_track_owner()")
    else:
        for name in ("graph_attribution_owner_insert", "graph_attribution_owner_update", "graph_track_owner"):
            schema_editor.execute(f"DROP TRIGGER {name}")
    for operation in ("insert", "delete", "update"):
        name = f"graph_attribution_{operation}"
        if schema_editor.connection.vendor == "postgresql":
            schema_editor.execute(f"DROP TRIGGER {name} ON {ATTRIBUTION}")
            schema_editor.execute(f"DROP FUNCTION {name}()")
        else:
            schema_editor.execute(f"DROP TRIGGER {name}")


class Migration(migrations.Migration):
    dependencies = [("the_music_tree_genre_kit", "0016_semantic_genre_graph")]
    operations = [migrations.RunPython(install, uninstall)]
