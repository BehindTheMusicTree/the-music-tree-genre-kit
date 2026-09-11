import json
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from the_music_tree_genre_kit.serializer.model.track.input.song_seed.Fields import Fields
from the_music_tree_genre_kit.serializer.model.track.input.song_seed.import_serializer import (
    SongSeedImportSerializer,
)
from the_music_tree_genre_kit.track.Track import Track


class SongSeedTreeMixin[T: Track]:
    """
    Adds a `songs/load-seed` action, seeding the current user's track library
    from a JSON fixture the consuming app ships under `settings.DATA_DIR`. Mix
    into an `AppModelViewSet[T]` subclass for a track viewset.

    To use the shared fixture bundled with this package instead of an app-local
    copy, point `settings.DATA_DIR` at `the_music_tree_genre_kit.data.DATA_DIR`.
    """

    model_class: type[T]
    seed_songs_filename: str = "song_seed.json"

    def get_seed_songs_data_path(self) -> Path:
        return settings.DATA_DIR / self.seed_songs_filename

    def on_seed_songs_loaded(self, request) -> None:
        """Hook for app-specific side effects after seed songs are imported."""

    @action(detail=False, methods=["post"], url_path="songs/load-seed")
    def load_seed_songs(self, request):
        data_path = self.get_seed_songs_data_path()

        if not data_path.exists():
            raise FileNotFoundError(f"Seed songs file not found at {data_path}")

        with open(data_path) as f:
            data = json.load(f)

        serializer = SongSeedImportSerializer(data={Fields.SONGS: data})
        serializer.is_valid(raise_exception=True)

        self.model_class.objects.import_seed_songs(request.user, serializer.validated_data[Fields.SONGS])
        self.on_seed_songs_loaded(request)

        return Response({"message": "Seed songs loaded successfully"}, status=status.HTTP_201_CREATED)
