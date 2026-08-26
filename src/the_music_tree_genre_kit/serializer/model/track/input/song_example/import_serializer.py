from rest_framework.fields import ListField
from the_music_tree_api_kit.serializer.AppInputSerializer import AppInputSerializer

from .entry_serializer import SongExampleEntrySerializer


class SongExampleImportSerializer(AppInputSerializer):
    # Plain DRF ListField, not AppListField: AppListField's to_internal_value resolves
    # (via MRO) to AppField's, which always returns None - a no-op stub meant to be
    # overridden by leaf field subclasses, never exercised with a Serializer child
    # elsewhere in this codebase. AppInputSerializer._validate_field already converts
    # any DRF ValidationError raised here into AppValidationException, so error handling
    # stays consistent with the rest of the serializer.
    songs = ListField(child=SongExampleEntrySerializer(), allow_empty=False)
