import json
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from the_music_tree_genre_kit.serializer.model.track.input.song_example.Fields import Fields
from the_music_tree_genre_kit.serializer.model.track.input.song_example.import_serializer import (
    SongExampleImportSerializer,
)
from the_music_tree_genre_kit.track.Track import Track


class SongExampleTreeMixin[T: Track]:
    """
    Adds a `songs/load-example` action, seeding the current user's track library
    from a JSON fixture the consuming app ships under `settings.DATA_DIR`. Mix
    into an `AppModelViewSet[T]` subclass for a track viewset.

    To use the shared fixture bundled with this package instead of an app-local
    copy, point `settings.DATA_DIR` at `the_music_tree_genre_kit.data.DATA_DIR`.
    """

    model_class: type[T]
    example_songs_filename: str = "song_example.json"

    def get_example_songs_data_path(self) -> Path:
        return settings.DATA_DIR / self.example_songs_filename

    def on_example_songs_loaded(self, request) -> None:
        """Hook for app-specific side effects after example songs are imported."""

    @action(detail=False, methods=["post"], url_path="songs/load-example")
    def load_example_songs(self, request):
        data_path = self.get_example_songs_data_path()

        if not data_path.exists():
            raise FileNotFoundError(f"Example songs file not found at {data_path}")

        with open(data_path) as f:
            data = json.load(f)

        serializer = SongExampleImportSerializer(data={Fields.SONGS: data})
        serializer.is_valid(raise_exception=True)

        self.model_class.objects.import_example_songs(request.user, serializer.validated_data[Fields.SONGS])
        self.on_example_songs_loaded(request)

        return Response({"message": "Example songs loaded successfully"}, status=status.HTTP_201_CREATED)
