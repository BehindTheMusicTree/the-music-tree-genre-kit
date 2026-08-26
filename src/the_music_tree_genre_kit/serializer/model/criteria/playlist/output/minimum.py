from rest_framework import serializers
from the_music_tree_api_kit.uuid.Fields import Fields as UuidFields

from the_music_tree_genre_kit.criteria.playlist.AbstractCriteriaPlaylist import AbstractCriteriaPlaylist
from the_music_tree_genre_kit.criteria.playlist.Fields import Fields as CriteriaPlaylistFields


def build_criteria_playlist_minimum_serializer(
    criteria_playlist_model: type[AbstractCriteriaPlaylist],
) -> type[serializers.ModelSerializer]:
    """DRF's ModelSerializer rejects an abstract Meta.model, so each consumer must supply its own concrete subclass."""

    class CriteriaPlaylistMinimumSerializer(serializers.ModelSerializer):
        class Meta:
            model = criteria_playlist_model
            fields = [UuidFields.UUID, CriteriaPlaylistFields.NAME]

    return CriteriaPlaylistMinimumSerializer
