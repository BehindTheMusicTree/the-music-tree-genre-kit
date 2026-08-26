from django.conf import settings
from the_music_tree_api_kit.serializer.AppInputSerializer import AppInputSerializer
from the_music_tree_api_kit.serializer.field.AppCharField import AppCharField


class SongExampleEntrySerializer(AppInputSerializer):
    title = AppCharField(max_length=settings.TRACK_TITLE_LEN_MAX, allow_blank=False, required=True)
    artist = AppCharField(max_length=255, allow_blank=False, required=True)
    youtube_video_id = AppCharField(max_length=32, allow_blank=False, required=True)
    genre_name = AppCharField(max_length=settings.CRITERIA_NAME_LEN_MAX, allow_blank=False, required=True)
