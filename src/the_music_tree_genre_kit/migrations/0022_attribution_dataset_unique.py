"""One node per track and dataset: denormalize dataset_id and enforce UNIQUE(dataset_id, track_id)."""

import django.db.models.deletion
from importlib import import_module

from django.db import migrations, models

PREFIX = "the_music_tree_genre_kit_"
A = PREFIX + "genregraphattribution"
N = PREFIX + "genregraphnode"


def _guards(name):
    return import_module(f"the_music_tree_genre_kit.migrations.{name}")


def suspend_triggers(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "sqlite":
        # SQLite rebuilds the table, which drops its triggers; reinstall them afterwards.
        _guards("0021_assignment_guards").uninstall(apps, schema_editor)
        _guards("0017_graph_attribution_invalidation").uninstall(apps, schema_editor)
    else:
        # The backfill must not bump assignment CAS tokens or membership revisions.
        schema_editor.execute(f"ALTER TABLE {A} DISABLE TRIGGER USER")


def resume_triggers(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "sqlite":
        _guards("0017_graph_attribution_invalidation").install(apps, schema_editor)
        _guards("0021_assignment_guards").install(apps, schema_editor)
    else:
        schema_editor.execute(f"ALTER TABLE {A} ENABLE TRIGGER USER")


def backfill(apps, schema_editor):
    schema_editor.execute(f"UPDATE {A} SET dataset_id = (SELECT n.dataset_id FROM {N} n WHERE n.id = {A}.node_id)")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"""SELECT dataset_id, track_id, count(*) FROM {A}
            GROUP BY dataset_id, track_id HAVING count(*) > 1 ORDER BY dataset_id, track_id LIMIT 1""")
        duplicate = cursor.fetchone()
    if duplicate:
        raise RuntimeError(
            f"Track {duplicate[1]} has {duplicate[2]} nodes in dataset {duplicate[0]}; "
            "keep one node per track and dataset before migrating"
        )


def install_guards(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        schema_editor.execute(f"""ALTER TABLE {A} ADD CONSTRAINT graph_attribution_node_dataset_fk
            FOREIGN KEY (dataset_id, node_id) REFERENCES {N} (dataset_id, id) DEFERRABLE INITIALLY DEFERRED""")
        schema_editor.execute("""CREATE FUNCTION graph_attribution_dataset_immutable() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
                IF NEW.dataset_id <> OLD.dataset_id THEN
                    RAISE EXCEPTION 'Attribution dataset is immutable' USING ERRCODE = '23514';
                END IF; RETURN NEW; END $$""")
        schema_editor.execute(f"""CREATE TRIGGER graph_attribution_dataset_immutable BEFORE UPDATE ON {A}
            FOR EACH ROW EXECUTE FUNCTION graph_attribution_dataset_immutable()""")
    else:
        schema_editor.execute(f"""CREATE TRIGGER graph_attribution_node_dataset_insert BEFORE INSERT ON {A}
            WHEN NOT EXISTS (SELECT 1 FROM {N} WHERE id = NEW.node_id AND dataset_id = NEW.dataset_id)
            BEGIN SELECT RAISE(ABORT, 'Attribution dataset must match its node'); END""")
        schema_editor.execute(f"""CREATE TRIGGER graph_attribution_node_dataset_update BEFORE UPDATE ON {A}
            WHEN NOT EXISTS (SELECT 1 FROM {N} WHERE id = NEW.node_id AND dataset_id = NEW.dataset_id)
                OR NEW.dataset_id <> OLD.dataset_id
            BEGIN SELECT RAISE(ABORT, 'Attribution dataset must match its node'); END""")


def uninstall_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f"ALTER TABLE {A} DROP CONSTRAINT graph_attribution_node_dataset_fk")
        schema_editor.execute(f"DROP TRIGGER graph_attribution_dataset_immutable ON {A}")
        schema_editor.execute("DROP FUNCTION graph_attribution_dataset_immutable()")
    else:
        schema_editor.execute("DROP TRIGGER graph_attribution_node_dataset_insert")
        schema_editor.execute("DROP TRIGGER graph_attribution_node_dataset_update")


class Migration(migrations.Migration):
    dependencies = [("the_music_tree_genre_kit", "0021_assignment_guards")]

    operations = [
        migrations.RunPython(suspend_triggers, resume_triggers),
        migrations.AddField(
            model_name="genregraphattribution",
            name="dataset",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attributions",
                to="the_music_tree_genre_kit.genregraphdataset",
            ),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="genregraphattribution",
            name="dataset",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attributions",
                to="the_music_tree_genre_kit.genregraphdataset",
            ),
        ),
        migrations.RemoveConstraint(model_name="genregraphattribution", name="graph_attribution_unique"),
        migrations.AddConstraint(
            model_name="genregraphattribution",
            constraint=models.UniqueConstraint(
                fields=("dataset", "track"), name="graph_attribution_dataset_track_unique"
            ),
        ),
        migrations.RunPython(install_guards, uninstall_guards),
        migrations.RunPython(resume_triggers, suspend_triggers),
    ]
