from django.db import migrations, models

INDEX = models.Index(fields=["user", "title"], name="the_music_t_user_id_db716d_idx")


# Plain DROP INDEX queues an ACCESS EXCLUSIVE lock behind a running songs merge and blocks every read on
# the 30M-row track table until it ends; CONCURRENTLY doesn't. SQLite (tests) has no concurrent variant.
# IF EXISTS: a concurrent drop killed mid-way leaves an INVALID index, and a re-run must still finish it.
def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {schema_editor.quote_name(INDEX.name)}")
    else:
        schema_editor.remove_index(apps.get_model("the_music_tree_genre_kit", "Track"), INDEX)


# Reverse is a no-op: titles now reach 2048 chars (~8 KB), past the 2704-byte btree row limit, so the index can't
# be rebuilt once a long title is stored. Nothing queries it, so leaving it absent on rollback is harmless.
class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("the_music_tree_genre_kit", "0010_track_title_len_2048"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.RemoveIndex(model_name="track", name=INDEX.name)],
            database_operations=[migrations.RunPython(drop_index, migrations.RunPython.noop)],
        ),
    ]
