import re

from django.conf import settings
from django.core.checks import Error

_MODEL_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")

_REQUIRED_SETTINGS = [
    "CRITERIA_MODEL",
    "TRACK_MODEL",
    "ARTIST_MODEL",
    "ALBUM_MODEL",
    "TRACK_PLAYLIST_REL_MODEL",
]


def check_swappable_model_settings(app_configs, **kwargs):
    errors = []
    for setting_name in _REQUIRED_SETTINGS:
        value = getattr(settings, setting_name, None)
        if not value or not isinstance(value, str) or not _MODEL_LABEL_RE.match(value):
            errors.append(
                Error(
                    f'settings.{setting_name} must be set to an "app_label.ModelName" string.',
                    id="the_music_tree_genre_kit.E001",
                )
            )
    return errors
