from django.db import migrations, models


def _rename(apps, old, new):
    apps.get_model("fixture_app", "Criteria").objects.filter(tree_name=old).update(tree_name=new)


def forward(apps, schema_editor):
    _rename(apps, "canonical", "global")


def backward(apps, schema_editor):
    _rename(apps, "global", "canonical")


class Migration(migrations.Migration):
    dependencies = [
        ("fixture_app", "0026_genre_image"),
    ]

    operations = [
        migrations.AlterField(
            model_name="criteria",
            name="tree_name",
            field=models.CharField(
                choices=[("global", "Global"), ("regional", "Regional")], default="global", max_length=16
            ),
        ),
        migrations.RunPython(forward, backward),
    ]
