from importlib import import_module
from django.db import migrations, models
import django.db.models.deletion


def suspend_triggers(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        import_module("the_music_tree_genre_kit.migrations.0017_graph_attribution_invalidation").uninstall(
            apps, schema_editor
        )


def resume_triggers(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        import_module("the_music_tree_genre_kit.migrations.0017_graph_attribution_invalidation").install(
            apps, schema_editor
        )


def populate(apps, schema_editor):
    access = apps.get_model("the_music_tree_genre_kit", "GenreGraphAccess")
    node = apps.get_model("the_music_tree_genre_kit", "GenreGraphNode")
    quote = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {quote(access._meta.db_table)} SET dataset_id = (SELECT dataset_id FROM {quote(node._meta.db_table)} n WHERE n.id = ancestor_id)"
        )


def ownership(apps, schema_editor):
    quote = schema_editor.quote_name
    access = quote(apps.get_model("the_music_tree_genre_kit", "GenreGraphAccess")._meta.db_table)
    node = quote(apps.get_model("the_music_tree_genre_kit", "GenreGraphNode")._meta.db_table)
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        for field in ("ancestor", "descendant"):
            schema_editor.execute(
                f"ALTER TABLE {access} ADD CONSTRAINT graph_access_{field}_dataset_fk FOREIGN KEY (dataset_id, {field}_id) REFERENCES {node} (dataset_id, id) DEFERRABLE INITIALLY IMMEDIATE"
            )
        schema_editor.execute("""CREATE FUNCTION graph_node_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.dataset_id IS DISTINCT FROM OLD.dataset_id OR NEW.identity IS DISTINCT FROM OLD.identity THEN
            RAISE EXCEPTION 'Graph node identity is immutable' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$""")
        schema_editor.execute(
            f"CREATE TRIGGER graph_node_identity_guard BEFORE UPDATE ON {node} FOR EACH ROW EXECUTE FUNCTION graph_node_identity_guard()"
        )
    elif vendor == "sqlite":
        for operation in ("INSERT", "UPDATE"):
            schema_editor.execute(f"""CREATE TRIGGER graph_access_dataset_{operation.lower()} BEFORE {operation} ON {access}
            WHEN NOT EXISTS (SELECT 1 FROM {node} WHERE id = NEW.ancestor_id AND dataset_id = NEW.dataset_id)
              OR NOT EXISTS (SELECT 1 FROM {node} WHERE id = NEW.descendant_id AND dataset_id = NEW.dataset_id)
            BEGIN SELECT RAISE(ABORT, 'Graph access endpoints must belong to dataset'); END""")
        schema_editor.execute(f"""CREATE TRIGGER graph_node_identity_guard BEFORE UPDATE ON {node}
        WHEN NEW.dataset_id <> OLD.dataset_id OR NEW.identity <> OLD.identity
        BEGIN SELECT RAISE(ABORT, 'Graph node identity is immutable'); END""")
    else:
        raise RuntimeError("Reference graphs require PostgreSQL or SQLite")


def remove_ownership(apps, schema_editor):
    access = schema_editor.quote_name(apps.get_model("the_music_tree_genre_kit", "GenreGraphAccess")._meta.db_table)
    node = schema_editor.quote_name(apps.get_model("the_music_tree_genre_kit", "GenreGraphNode")._meta.db_table)
    if schema_editor.connection.vendor == "postgresql":
        for field in ("ancestor", "descendant"):
            schema_editor.execute(f"ALTER TABLE {access} DROP CONSTRAINT graph_access_{field}_dataset_fk")
        schema_editor.execute(f"DROP TRIGGER graph_node_identity_guard ON {node}")
        schema_editor.execute("DROP FUNCTION graph_node_identity_guard()")
    elif schema_editor.connection.vendor == "sqlite":
        for trigger in ("graph_access_dataset_insert", "graph_access_dataset_update", "graph_node_identity_guard"):
            schema_editor.execute(f"DROP TRIGGER {trigger}")


class Migration(migrations.Migration):
    dependencies = [("the_music_tree_genre_kit", "0018_graph_attribution_history")]
    operations = [
        migrations.RunPython(suspend_triggers, resume_triggers),
        migrations.AddField(model_name="genregraphrevision", name="retirements", field=models.JSONField(default=dict)),
        migrations.AddField(model_name="genregraphnode", name="is_active", field=models.BooleanField(default=True)),
        migrations.AddField(
            model_name="genregraphaccess",
            name="dataset",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="access",
                to="the_music_tree_genre_kit.genregraphdataset",
            ),
        ),
        migrations.RunPython(populate, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="genregraphaccess",
            name="dataset",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="access",
                to="the_music_tree_genre_kit.genregraphdataset",
            ),
        ),
        migrations.AddConstraint(
            model_name="genregraphnode",
            constraint=models.UniqueConstraint(fields=["dataset", "id"], name="graph_node_dataset_id_unique"),
        ),
        migrations.AddIndex(
            model_name="genregraphaccess",
            index=models.Index(fields=["dataset", "ancestor", "scope", "descendant"], name="graph_access_forward"),
        ),
        migrations.AddIndex(
            model_name="genregraphaccess",
            index=models.Index(fields=["dataset", "descendant", "scope", "ancestor"], name="graph_access_reverse"),
        ),
        migrations.RunPython(ownership, remove_ownership),
        migrations.RunPython(resume_triggers, suspend_triggers),
    ]
