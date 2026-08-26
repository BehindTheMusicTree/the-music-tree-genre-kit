from rest_framework import serializers
from rest_framework.fields import IntegerField

from the_music_tree_genre_kit.track_mixin.Fields import Fields as TrackMixinFields


def build_criteria_detailed_tracks_fields(
    track_serializer_class: type[serializers.ModelSerializer],
    tracks_field_name: str,
    tracks_count_field_name: str,
    tracks_archived_count_field_name: str,
) -> dict[str, serializers.Field]:
    """
    Returns a dict of DRF field instances sourced from `TrackMixin`'s
    properties, keyed by the caller's own public field names. Not a full
    serializer builder (unlike `minimum.py`/`simple.py`): each app's
    `CriteriaDetailedSerializer` mixes these with other app-specific fields,
    so the caller assigns the returned fields as class attributes itself:

        _tracks_fields = build_criteria_detailed_tracks_fields(
            TrackSerializer,
            CriteriaOutputFieldKey.TRACKS_NOT_ARCHIVED_PUBLIC.value,
            CriteriaOutputFieldKey.TRACKS_NOT_ARCHIVED_COUNT_PUBLIC.value,
            CriteriaOutputFieldKey.TRACKS_ARCHIVED_COUNT_PUBLIC.value,
        )

        class CriteriaDetailedSerializer(...):
            tracks = _tracks_fields[CriteriaOutputFieldKey.TRACKS_NOT_ARCHIVED_PUBLIC.value]
            tracks_count = _tracks_fields[CriteriaOutputFieldKey.TRACKS_NOT_ARCHIVED_COUNT_PUBLIC.value]
            tracks_archived_count = _tracks_fields[CriteriaOutputFieldKey.TRACKS_ARCHIVED_COUNT_PUBLIC.value]
    """

    def _source(internal_name: str, public_name: str) -> str | None:
        """DRF forbids a redundant `source` equal to the field's own name."""
        return internal_name if internal_name != public_name else None

    return {
        tracks_field_name: track_serializer_class(
            source=_source(TrackMixinFields.TRACKS_NOT_ARCHIVED_INTERNAL, tracks_field_name), many=True
        ),
        tracks_count_field_name: IntegerField(
            source=_source(TrackMixinFields.TRACKS_NOT_ARCHIVED_COUNT_INTERNAL, tracks_count_field_name)
        ),
        tracks_archived_count_field_name: IntegerField(
            source=_source(TrackMixinFields.TRACKS_ARCHIVED_COUNT_INTERNAL, tracks_archived_count_field_name)
        ),
    }
