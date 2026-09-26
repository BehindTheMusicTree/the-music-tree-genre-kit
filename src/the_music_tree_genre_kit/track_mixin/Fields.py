from the_music_tree_api_kit.private_unique_resource.Fields import Fields as PrivateUniqueResourceFields


class Fields(PrivateUniqueResourceFields):
    NAME_PUBLIC = "name"
    NAME_INTERNAL = f"_{NAME_PUBLIC}"
    TRACKS_INTERNAL = "tracks"
    TRACKS_PUBLIC = "tracks"
    TRACKS_SORTED_INTERNAL = f"{TRACKS_INTERNAL}_sorted"
    TRACKS_SORTED_PUBLIC = f"{TRACKS_PUBLIC}_sorted"
    TRACKS_COUNT_INTERNAL = f"{TRACKS_INTERNAL}_count"
    TRACKS_COUNT_PUBLIC = f"{TRACKS_PUBLIC}_count"
