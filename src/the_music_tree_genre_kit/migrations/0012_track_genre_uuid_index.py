import django.db.models.deletion
import the_music_tree_api_kit.field.foreign_key.PrivateForeignKey
from django.conf import settings
from django.db import migrations, models

INDEX = models.Index(fields=["genre", "uuid"], name="track_genre_uuid_idx")


# Plain CREATE/DROP INDEX locks writes (or queues an ACCESS EXCLUSIVE lock) on the 30M-row track table;
# CONCURRENTLY doesn't. SQLite (tests) has no concurrent variant and keeps its plain FK index.
# IF [NOT] EXISTS: a concurrent build killed mid-way leaves an INVALID index, so a re-run drops it first.
def add_index(apps, schema_editor):
    track = apps.get_model("the_music_tree_genre_kit", "Track")
    if schema_editor.connection.vendor != "postgresql":
        schema_editor.add_index(track, INDEX)
        return
    quote = schema_editor.quote_name
    schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {quote(INDEX.name)}")
    schema_editor.execute(
        f"CREATE INDEX CONCURRENTLY {quote(INDEX.name)} ON {quote(track._meta.db_table)} (genre_id, uuid)"
    )


# The (genre_id, uuid) index serves every genre_id lookup, so the plain FK index is dead write overhead.
def drop_fk_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    track = apps.get_model("the_music_tree_genre_kit", "Track")
    with schema_editor.connection.cursor() as cursor:
        constraints = schema_editor.connection.introspection.get_constraints(cursor, track._meta.db_table)
    for name, info in constraints.items():
        if info["columns"] == ["genre_id"] and info["index"] and not info["unique"] and not info["primary_key"]:
            schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {schema_editor.quote_name(name)}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("the_music_tree_genre_kit", "0011_remove_track_user_title_index"),
        migrations.swappable_dependency(settings.CRITERIA_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.AddIndex(model_name="track", index=INDEX)],
            database_operations=[migrations.RunPython(add_index, migrations.RunPython.noop)],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="track",
                    name="genre",
                    field=the_music_tree_api_kit.field.foreign_key.PrivateForeignKey.PrivateForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="tracks_of_criteria",
                        to=settings.CRITERIA_MODEL,
                    ),
                ),
            ],
            database_operations=[migrations.RunPython(drop_fk_index, migrations.RunPython.noop)],
        ),
    ]
