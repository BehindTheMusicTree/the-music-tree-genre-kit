from typing import TYPE_CHECKING, TypeVar

from .Fields import Fields
from .TrackMixinManager import TrackMixinManager

if TYPE_CHECKING:
    from .TrackMixin import TrackMixin

T = TypeVar("T", bound="TrackMixin")


class TrackMixinWithInternalNameManager(TrackMixinManager[T]):
    def get_default_ordering(self) -> list[str]:
        return [Fields.NAME_INTERNAL]
