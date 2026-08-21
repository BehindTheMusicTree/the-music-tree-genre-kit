from the_music_tree_api_kit.trackable_play_count.Fields import Fields as TrackablePlayCountFields


class Fields(TrackablePlayCountFields):
    TITLE = "title"
    ARTISTS = "artists"
    ALBUM = "album"
    TRACK_NUMBER = "track_number"
    GENRE = "genre"
    RATING = "rating"
    LANGUAGE = "language"
    ARCHIVED = "archived"

    TRACKS_OF_ARTIST_RELATED_NAME = "tracks_of_artist"
    TRACKS_OF_ALBUM_RELATED_NAME = "tracks_of_album"
    TRACKS_OF_CRITERIA_RELATED_NAME = "tracks_of_criteria"
