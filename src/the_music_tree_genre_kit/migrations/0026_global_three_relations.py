"""Graph contract 5: ``global`` state and roots, ``regional_membership`` folded into ``classification``.

Datasets and revisions are converted in place so stored graphs stay loadable and restorable. The
migration is self-contained: it does not import the graph package, whose contract keeps moving.
"""

from django.db import migrations

P = "the_music_tree_genre_kit_"
REVISION_TABLE = P + "genregraphrevision"
REVISION_GUARD = "genregraphrevision_immutable_update"


def to_v5(payload):
    if payload.get("contractVersion") != 4:
        return None
    result = {key: value for key, value in payload.items() if key != "canonicalRoots"}
    result["contractVersion"] = 5
    result["globalRoots"] = payload["canonicalRoots"]
    result["relations"] = [
        {**r, "type": "classification"} if r["type"] == "regional_membership" else r for r in payload["relations"]
    ]
    return result


def to_v4(payload):
    # Not validated against contract 4: influence next to classification, accepted by 5, is invalid there.
    if payload.get("contractVersion") != 5:
        return None
    overviews = {node["id"] for node in payload["nodes"] if node["kind"] == "overview"}
    result = {key: value for key, value in payload.items() if key != "globalRoots"}
    result["contractVersion"] = 4
    result["canonicalRoots"] = payload["globalRoots"]
    result["relations"] = [
        {**r, "type": "regional_membership"} if r["type"] == "classification" and r["parentId"] in overviews else r
        for r in payload["relations"]
    ]
    return result


def _without_revision_guard(schema_editor, update):
    """Revisions are immutable (0021): lift the update trigger for this rewrite only."""
    postgresql = schema_editor.connection.vendor == "postgresql"
    schema_editor.execute(f"DROP TRIGGER {REVISION_GUARD}" + (f" ON {REVISION_TABLE}" if postgresql else ""))
    update()
    if postgresql:  # the function is kept, only the trigger is recreated
        schema_editor.execute(f"""CREATE TRIGGER {REVISION_GUARD} BEFORE UPDATE ON {REVISION_TABLE}
            FOR EACH ROW EXECUTE FUNCTION {REVISION_GUARD}()""")
    else:
        schema_editor.execute(f"""CREATE TRIGGER {REVISION_GUARD} BEFORE UPDATE ON {REVISION_TABLE}
            BEGIN SELECT RAISE(ABORT, 'Graph evidence and audit are immutable'); END""")


def _rewrite(model, alias, convert):
    for row in model.objects.using(alias).only("pk", "payload").iterator():
        if (converted := convert(row.payload)) is not None:
            model.objects.using(alias).filter(pk=row.pk).update(payload=converted)


def _convert(apps, schema_editor, convert):
    alias = schema_editor.connection.alias
    _rewrite(apps.get_model("the_music_tree_genre_kit", "GenreGraphDataset"), alias, convert)
    revision = apps.get_model("the_music_tree_genre_kit", "GenreGraphRevision")
    _without_revision_guard(schema_editor, lambda: _rewrite(revision, alias, convert))


def payloads_forward(apps, schema_editor):
    _convert(apps, schema_editor, to_v5)


def payloads_backward(apps, schema_editor):
    _convert(apps, schema_editor, to_v4)


def _rename_state(apps, schema_editor, old, new):
    node = apps.get_model("the_music_tree_genre_kit", "GenreGraphNode")
    node.objects.using(schema_editor.connection.alias).filter(state=old).update(state=new)


def states_forward(apps, schema_editor):
    _rename_state(apps, schema_editor, "canonical", "global")


def states_backward(apps, schema_editor):
    _rename_state(apps, schema_editor, "global", "canonical")


class Migration(migrations.Migration):
    dependencies = [
        ("the_music_tree_genre_kit", "0025_staged_publication_bypass"),
    ]

    operations = [
        migrations.RenameField(model_name="genregraphnode", old_name="canonical_state", new_name="state"),
        migrations.RunPython(states_forward, states_backward),
        migrations.RunPython(payloads_forward, payloads_backward),
    ]
