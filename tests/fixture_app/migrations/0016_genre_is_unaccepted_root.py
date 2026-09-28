from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fixture_app", "0015_remove_genre_unique_wikidata_id_per_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="genre",
            name="is_unaccepted_root",
            field=models.BooleanField(default=False),
        ),
    ]
