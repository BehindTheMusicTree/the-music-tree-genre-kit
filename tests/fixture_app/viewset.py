from rest_framework import serializers
from the_music_tree_api_kit.view.viewset.model.AppModelViewSet import AppModelViewSet

from tests.fixture_app.models import Criteria, CriteriaPlaylist, Track, TrackPlaylistRel
from the_music_tree_genre_kit.serializer.model.criteria.output.simple import build_criteria_simple_serializer
from the_music_tree_genre_kit.view.viewset.AbstractCriteriaViewSet import AbstractCriteriaViewSet
from the_music_tree_genre_kit.view.viewset.playlist.PlaylistTracksActionMixin import PlaylistTracksActionMixin
from the_music_tree_genre_kit.view.viewset.track.SongsImportMixin import SongsImportMixin


class CriteriaViewSet(AbstractCriteriaViewSet[Criteria]):
    def __init__(self, **kwargs):
        super().__init__(
            model_class=Criteria,
            simple_serializer_class=build_criteria_simple_serializer(Criteria),
            **kwargs,
        )


class TrackViewSet(SongsImportMixin[Track], AppModelViewSet[Track]):
    def __init__(self, **kwargs):
        super().__init__(model_class=Track, **kwargs)


class TrackPlaylistRelSerializer(serializers.ModelSerializer):
    track = serializers.UUIDField(source="track.uuid")

    class Meta:
        model = TrackPlaylistRel
        fields = ["position", "track"]


class CriteriaPlaylistViewSet(PlaylistTracksActionMixin, AppModelViewSet[CriteriaPlaylist]):
    track_playlist_rel_serializer_class = TrackPlaylistRelSerializer

    def __init__(self, **kwargs):
        super().__init__(model_class=CriteriaPlaylist, **kwargs)
