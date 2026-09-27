from django.db import migrations, models
from django.db.models import F


def dedupe_and_renumber(apps, schema_editor):
    TrackPlaylistRel = apps.get_model("the_music_tree_genre_kit", "TrackPlaylistRel")
    seen: set[tuple[int, int]] = set()
    duplicate_pks = []
    rels = TrackPlaylistRel.objects.order_by(
        "playlist_id", "track_id", F("position").asc(nulls_last=True), "created_on", "pk"
    ).values_list("pk", "playlist_id", "track_id")
    for pk, playlist_id, track_id in rels.iterator():
        if (playlist_id, track_id) in seen:
            duplicate_pks.append(pk)
        else:
            seen.add((playlist_id, track_id))
    for start in range(0, len(duplicate_pks), 1000):
        TrackPlaylistRel.objects.filter(pk__in=duplicate_pks[start : start + 1000]).delete()

    to_update = []
    playlist_id = None
    position = 0
    positioned = TrackPlaylistRel.objects.filter(position__isnull=False).order_by("playlist_id", "position", "pk")
    for rel in positioned.only("pk", "playlist_id", "position").iterator():
        if rel.playlist_id != playlist_id:
            playlist_id = rel.playlist_id
            position = 0
        position += 1
        if rel.position != position:
            rel.position = position
            to_update.append(rel)
    TrackPlaylistRel.objects.bulk_update(to_update, ["position"], batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ("the_music_tree_genre_kit", "0008_remove_track_archived"),
    ]

    operations = [
        migrations.RunPython(dedupe_and_renumber, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="trackplaylistrel",
            constraint=models.UniqueConstraint(fields=("playlist", "track"), name="uniq_track_playlist_rel"),
        ),
    ]
