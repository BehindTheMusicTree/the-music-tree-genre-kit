from django.db.models import F
from rest_framework.decorators import action
from rest_framework.serializers import Serializer
from the_music_tree_api_kit.view.viewset.model.AppModelViewSet import AppModelViewSet

from the_music_tree_genre_kit.criteria.track_playlist_rel.Fields import Fields
from the_music_tree_genre_kit.criteria.track_playlist_rel.TrackPlaylistRel import TrackPlaylistRel


class PlaylistTracksActionMixin:
    """
    Adds a paginated `{uuid}/tracks` action listing the playlist's track relations in
    play order (position ascending, unpositioned last). Mix into an `AppModelViewSet`
    subclass for a playlist viewset and set `track_playlist_rel_serializer_class`.
    """

    track_playlist_rel_serializer_class: type[Serializer]

    @action(detail=True, methods=["get"], url_path="tracks")
    def tracks(self, request, *args, **kwargs):
        playlist = self.get_object()  # type: ignore[attr-defined]
        queryset = TrackPlaylistRel.objects.filter(**{Fields.PLAYLIST: playlist.pk}).order_by(
            F(Fields.POSITION).asc(nulls_last=True), "pk"
        )
        serializer_class = self.track_playlist_rel_serializer_class
        page = self.paginate_queryset(AppModelViewSet._eager_load(serializer_class, queryset))  # type: ignore[attr-defined]
        return self.get_paginated_response(serializer_class(page, many=True).data)  # type: ignore[attr-defined]
