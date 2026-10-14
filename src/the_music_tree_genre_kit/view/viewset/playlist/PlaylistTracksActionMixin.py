import uuid

from django.db.models import F, Q
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.serializers import Serializer
from the_music_tree_api_kit.view.viewset.model.AppModelViewSet import AppModelViewSet

from the_music_tree_genre_kit.criteria.track_playlist_rel.Fields import Fields
from the_music_tree_genre_kit.criteria.track_playlist_rel.TrackPlaylistRel import TrackPlaylistRel

FROM_QUERY_PARAM = "from"


class PlaylistTracksActionMixin:
    """
    Adds a paginated `{uuid}/tracks` action listing the playlist's track relations in
    play order (position ascending, unpositioned last). Mix into an `AppModelViewSet`
    subclass for a playlist viewset and set `track_playlist_rel_serializer_class`.

    `?from=<track uuid>` starts the list at that track's relation (inclusive); 404 if the
    track is not in the playlist, 400 if the value is not a UUID.
    """

    track_playlist_rel_serializer_class: type[Serializer]

    @action(detail=True, methods=["get"], url_path="tracks")
    def tracks(self, request, *args, **kwargs):
        playlist = self.get_object()  # type: ignore[attr-defined]
        queryset = TrackPlaylistRel.objects.filter(**{Fields.PLAYLIST: playlist.pk})
        from_track = request.query_params.get(FROM_QUERY_PARAM)
        if from_track is not None:
            queryset = queryset.filter(_at_or_after(_anchor_rel(queryset, from_track)))
        queryset = queryset.order_by(F(Fields.POSITION).asc(nulls_last=True), "pk")
        serializer_class = self.track_playlist_rel_serializer_class
        page = self.paginate_queryset(AppModelViewSet._eager_load(serializer_class, queryset))  # type: ignore[attr-defined]
        return self.get_paginated_response(serializer_class(page, many=True).data)  # type: ignore[attr-defined]


def _anchor_rel(queryset, track_uuid: str) -> TrackPlaylistRel:
    try:
        uuid.UUID(track_uuid)
    except ValueError:
        raise ValidationError({FROM_QUERY_PARAM: "Must be a track UUID."}) from None
    anchor = queryset.filter(**{f"{Fields.TRACK_INTERNAL}__uuid": track_uuid}).first()
    if anchor is None:
        raise NotFound(f"Track {track_uuid} is not in this playlist.")
    return anchor


def _at_or_after(anchor: TrackPlaylistRel) -> Q:
    """Rels at or after `anchor` in play order: position ascending, nulls last, then pk."""
    unpositioned_from_anchor = Q(**{f"{Fields.POSITION}__isnull": True, "pk__gte": anchor.pk})
    if anchor.position is None:
        return unpositioned_from_anchor
    return (
        Q(**{f"{Fields.POSITION}__gt": anchor.position})
        | Q(**{Fields.POSITION: anchor.position, "pk__gte": anchor.pk})
        | Q(**{f"{Fields.POSITION}__isnull": True})
    )
