from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from the_music_tree_genre_kit.serializer.model.track.input.song_seed.entry_serializer import (
    SongSeedEntrySerializer,
)
from the_music_tree_genre_kit.track.Track import Track


class SongsImportMixin[T: Track]:
    """
    Adds a `songs/import` action accepting an arbitrary flat list of
    {"title", "artist", "youtube_video_id", "genre_name"} entries, replacing all of the
    current user's tracks. Unlike `SongSeedTreeMixin`'s `songs/load-seed`, the payload
    comes from the request body rather than a bundled fixture file. Mix into an
    `AppModelViewSet[T]` subclass for a track viewset.
    """

    model_class: type[T]

    @action(detail=False, methods=["post"], url_path="songs/import")
    def import_songs(self, request):
        serializer = SongSeedEntrySerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        counts = self.model_class.objects.import_seed_songs(request.user, serializer.validated_data)
        return Response(counts, status=status.HTTP_201_CREATED)
