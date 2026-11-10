from django.db import migrations, models

INDEX = models.Index(fields=["playlist", "genre", "position", "id"], name="tpr_playlist_genre_pos_idx")


# CONCURRENTLY: a plain CREATE INDEX blocks writes on the ~440k-row rel table. SQLite (tests) has no concurrent
# variant. IF EXISTS first: a build killed mid-way leaves an INVALID index.
def add_index(apps, schema_editor):
    rel = apps.get_model("the_music_tree_genre_kit", "TrackPlaylistRel")
    if schema_editor.connection.vendor != "postgresql":
        schema_editor.add_index(rel, INDEX)
        return
    quote = schema_editor.quote_name
    schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {quote(INDEX.name)}")
    schema_editor.execute(
        f"CREATE INDEX CONCURRENTLY {quote(INDEX.name)} "
        f"ON {quote(rel._meta.db_table)} (playlist_id, genre_id, position, id)"
    )


def drop_index(apps, schema_editor):
    rel = apps.get_model("the_music_tree_genre_kit", "TrackPlaylistRel")
    if schema_editor.connection.vendor != "postgresql":
        schema_editor.remove_index(rel, INDEX)
        return
    schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {schema_editor.quote_name(INDEX.name)}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("the_music_tree_genre_kit", "0014_trackplaylistrel_genre"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.AddIndex(model_name="trackplaylistrel", index=INDEX)],
            database_operations=[migrations.RunPython(add_index, drop_index)],
        ),
    ]
