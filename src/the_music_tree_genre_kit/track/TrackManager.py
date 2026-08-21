from typing import TYPE_CHECKING, TypeVar

from .AbstractTrackManager import AbstractTrackManager

if TYPE_CHECKING:
    from .Track import Track

T = TypeVar("T", bound="Track")


class TrackManager(AbstractTrackManager[T]):
    model: type[T]
