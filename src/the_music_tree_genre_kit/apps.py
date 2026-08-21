from django.apps import AppConfig
from django.core.checks import register


class TheMusicTreeGenreKitConfig(AppConfig):
    name = "the_music_tree_genre_kit"
    label = "the_music_tree_genre_kit"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from .checks import check_swappable_model_settings

        register(check_swappable_model_settings)
