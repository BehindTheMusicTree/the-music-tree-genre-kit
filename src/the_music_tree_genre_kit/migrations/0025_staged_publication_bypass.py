"""Let a validated staged publication skip row-level guards that it already enforces set-wise."""

from django.db import migrations

P = "the_music_tree_genre_kit_"
A = P + "genregraphattribution"
L = P + "genregraphattributionevidence"

SETTING = "the_music_tree_genre_kit.staged_publication"
OFF = f"current_setting('{SETTING}', true) IS DISTINCT FROM 'on'"

ROW_TRIGGERS = (
    ("graph_attribution_owner", A, "INSERT OR UPDATE"),
    ("graph_active_attribution_insert", A, "INSERT"),
    ("graph_active_attribution_update", A, "UPDATE"),
    ("graph_evidence_dataset_insert", L, "INSERT"),
    ("graph_evidence_dataset_update", L, "UPDATE"),
)
REFERENCING = {
    "insert": "NEW TABLE AS new_rows",
    "update": "OLD TABLE AS old_rows NEW TABLE AS new_rows",
    "delete": "OLD TABLE AS old_rows",
}


def _recreate(schema_editor, when):
    clause = f"WHEN ({OFF}) " if when else ""
    for name, table, event in ROW_TRIGGERS:
        schema_editor.execute(f"DROP TRIGGER {name} ON {table}")
        schema_editor.execute(
            f"CREATE TRIGGER {name} BEFORE {event} ON {table} FOR EACH ROW {clause}EXECUTE FUNCTION {name}()"
        )
    for table, prefix in ((A, "graph_assignment_cas"), (L, "graph_evidence_cas")):
        for operation, referencing in REFERENCING.items():
            name = f"{prefix}_{operation}"
            schema_editor.execute(f"DROP TRIGGER {name} ON {table}")
            schema_editor.execute(
                f"CREATE TRIGGER {name} AFTER {operation.upper()} ON {table} REFERENCING {referencing} "
                f"FOR EACH STATEMENT {clause}EXECUTE FUNCTION {name}()"
            )


def install(apps, schema_editor):
    # SQLite triggers stay unconditional: it has no set-based publication cost to avoid.
    if schema_editor.connection.vendor == "postgresql":
        _recreate(schema_editor, when=True)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        _recreate(schema_editor, when=False)


class Migration(migrations.Migration):
    dependencies = [("the_music_tree_genre_kit", "0024_restrict_regional_access")]

    operations = [migrations.RunPython(install, uninstall)]
