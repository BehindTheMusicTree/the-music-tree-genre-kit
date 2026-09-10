from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from the_music_tree_genre_kit.serializer.model.track.input.song_example.entry_serializer import (
    SongExampleEntrySerializer,
)
from the_music_tree_genre_kit.track.Track import Track


class SongsImportMixin[T: Track]:
    """
    Adds a `songs/import` action accepting an arbitrary flat list of
    {"title", "artist", "youtube_video_id", "genre_name"} entries, replacing all of the
    current user's tracks. Unlike `SongExampleTreeMixin`'s `songs/load-example`, the payload
    comes from the request body rather than a bundled fixture file. Mix into an
    `AppModelViewSet[T]` subclass for a track viewset.
    """

    model_class: type[T]

    @action(detail=False, methods=["post"], url_path="songs/import")
    def import_songs(self, request):
        serializer = SongExampleEntrySerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.model_class.objects.import_example_songs(request.user, serializer.validated_data)
        return Response(status=status.HTTP_201_CREATED)
