"""Register package-owned semantic graph tables with Django."""

from .criteria.import_run.ImportRun import ImportRun
from .criteria.track_playlist_rel.TrackPlaylistRel import TrackPlaylistRel
from .criteria.type.CriteriaType import CriteriaType
from .genre_graph.models import (
    GenreGraphAccess,
    GenreGraphAttribution,
    GenreGraphAttributionRevision,
    GenreGraphDataset,
    GenreGraphNode,
    GenreGraphRevision,
)
from .playlist.Playlist import Playlist
from .track.Track import Track
