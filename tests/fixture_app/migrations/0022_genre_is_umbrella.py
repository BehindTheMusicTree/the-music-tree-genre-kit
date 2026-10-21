from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fixture_app', '0021_genre_description_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='genre',
            name='is_umbrella',
            field=models.BooleanField(default=False),
        ),
    ]
