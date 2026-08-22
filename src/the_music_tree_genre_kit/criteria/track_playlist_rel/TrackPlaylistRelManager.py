from typing import TYPE_CHECKING, TypeVar

from .AbstractTrackPlaylistRelManager import AbstractTrackPlaylistRelManager

if TYPE_CHECKING:
    from .TrackPlaylistRel import TrackPlaylistRel

T = TypeVar("T", bound="TrackPlaylistRel")


class TrackPlaylistRelManager(AbstractTrackPlaylistRelManager[T]):
    model: type[T]
