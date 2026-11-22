from uuid import uuid4

from django.db import migrations
from django.db.models import Exists, OuterRef


def restrict_access(apps, schema_editor):
    access = apps.get_model("the_music_tree_genre_kit", "GenreGraphAccess")
    datasets = apps.get_model("the_music_tree_genre_kit", "GenreGraphDataset")
    database = schema_editor.connection.alias
    extended = access.objects.using(database).filter(
        dataset_id=OuterRef("dataset_id"),
        ancestor_id=OuterRef("ancestor_id"),
        descendant_id=OuterRef("descendant_id"),
        scope="extended",
    )
    for key in datasets.objects.using(database).values_list("pk", flat=True).iterator():
        invalid = access.objects.using(database).filter(dataset_id=key, scope="restricted").filter(~Exists(extended))
        deleted, _ = invalid.delete()
        if deleted:
            datasets.objects.using(database).filter(pk=key).update(membership_revision=uuid4())


class Migration(migrations.Migration):
    dependencies = [("the_music_tree_genre_kit", "0023_graph_access_scopes")]

    operations = [migrations.RunPython(restrict_access)]
