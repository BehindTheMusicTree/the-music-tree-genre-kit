"""Contract 4 scopes (restricted, extended, expressions) replace all, canonical and regional.

The access index is derived from the stored graph, which a contract 4 re-import rebuilds, so
the old rows are dropped instead of being translated.
"""

from django.db import migrations, models


def clear_access(apps, schema_editor):
    apps.get_model("the_music_tree_genre_kit", "GenreGraphAccess").objects.all().delete()


def reinstall_access_guards(apps, schema_editor):
    # SQLite rebuilds the table to change a constraint, which drops its triggers (see 0019).
    if schema_editor.connection.vendor != "sqlite":
        return
    quote = schema_editor.quote_name
    access = quote(apps.get_model("the_music_tree_genre_kit", "GenreGraphAccess")._meta.db_table)
    node = quote(apps.get_model("the_music_tree_genre_kit", "GenreGraphNode")._meta.db_table)
    for operation in ("INSERT", "UPDATE"):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS graph_access_dataset_{operation.lower()}")
        schema_editor.execute(f"""CREATE TRIGGER graph_access_dataset_{operation.lower()} BEFORE {operation} ON {access}
        WHEN NOT EXISTS (SELECT 1 FROM {node} WHERE id = NEW.ancestor_id AND dataset_id = NEW.dataset_id)
          OR NOT EXISTS (SELECT 1 FROM {node} WHERE id = NEW.descendant_id AND dataset_id = NEW.dataset_id)
        BEGIN SELECT RAISE(ABORT, 'Graph access endpoints must belong to dataset'); END""")


class Migration(migrations.Migration):
    dependencies = [("the_music_tree_genre_kit", "0022_attribution_dataset_unique")]

    operations = [
        migrations.RunPython(clear_access, migrations.RunPython.noop),
        # Reverse order: this runs last on a downgrade, after the table rebuild dropped the triggers.
        migrations.RunPython(migrations.RunPython.noop, reinstall_access_guards),
        migrations.RemoveConstraint(model_name="genregraphaccess", name="graph_access_scope"),
        migrations.AddConstraint(
            model_name="genregraphaccess",
            constraint=models.CheckConstraint(
                condition=models.Q(scope__in=["restricted", "extended", "expressions"]), name="graph_access_scope"
            ),
        ),
        migrations.RunPython(reinstall_access_guards, migrations.RunPython.noop),
    ]
