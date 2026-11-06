from rest_framework import serializers

from the_music_tree_genre_kit.criteria.playlist.AbstractCriteriaPlaylist import AbstractCriteriaPlaylist
from the_music_tree_genre_kit.criteria.selection.counts import CriteriaCoverageCounts
from the_music_tree_genre_kit.serializer.model.criteria.playlist.output.minimum import (
    build_criteria_playlist_minimum_serializer,
)


class CriteriaCoverageCountsSerializer(serializers.Serializer):
    """Serialize prepared projections; missing or invalid counts are errors, never zeros."""

    genre_only_tracks_count = serializers.IntegerField(read_only=True)
    genre_and_subgenres_tracks_count = serializers.IntegerField(read_only=True)

    def to_representation(self, instance):
        counts = CriteriaCoverageCounts(
            genre_only_tracks_count=instance.genre_only_tracks_count,
            genre_and_subgenres_tracks_count=instance.genre_and_subgenres_tracks_count,
        )
        return super().to_representation(counts)


def build_criteria_playlist_summary_serializer(
    criteria_playlist_model: type[AbstractCriteriaPlaylist],
) -> type[serializers.ModelSerializer]:
    """Build a genre summary from annotations supplied by the consuming application."""
    minimum = build_criteria_playlist_minimum_serializer(criteria_playlist_model)

    class CriteriaPlaylistSummarySerializer(minimum):
        genre_only_tracks_count = serializers.IntegerField(read_only=True)
        genre_and_subgenres_tracks_count = serializers.IntegerField(read_only=True)

        def to_representation(self, instance):
            CriteriaCoverageCounts(instance.genre_only_tracks_count, instance.genre_and_subgenres_tracks_count)
            return super().to_representation(instance)

        class Meta:
            model = criteria_playlist_model
            fields = ["uuid", "name", "genre_only_tracks_count", "genre_and_subgenres_tracks_count"]

    return CriteriaPlaylistSummarySerializer
