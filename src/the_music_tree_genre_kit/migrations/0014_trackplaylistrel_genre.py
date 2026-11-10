import django.db.models.deletion
import the_music_tree_api_kit.field.foreign_key.PrivateForeignKey
from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("the_music_tree_genre_kit", "0013_trackplaylistrel_playlist_position_idx"),
        migrations.swappable_dependency(settings.CRITERIA_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="trackplaylistrel",
            name="genre",
            field=the_music_tree_api_kit.field.foreign_key.PrivateForeignKey.PrivateForeignKey(
                blank=True,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="track_playlist_rels_of_genre",
                to=settings.CRITERIA_MODEL,
            ),
        ),
    ]
