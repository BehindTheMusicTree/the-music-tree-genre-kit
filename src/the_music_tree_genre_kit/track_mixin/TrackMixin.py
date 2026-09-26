from abc import abstractmethod
from typing import TYPE_CHECKING

from django.db import models
from the_music_tree_api_kit.private_unique_resource.PrivateUniqueResource import PrivateUniqueResource

from .Fields import Fields

if TYPE_CHECKING:
    from the_music_tree_genre_kit.track.Track import Track


class TrackMixin(PrivateUniqueResource):
    class Meta:
        abstract = True

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def tracks(self) -> models.QuerySet[Track]:
        pass

    @property
    def tracks_sorted(self) -> models.QuerySet[Track]:
        return self.tracks.order_by(f"-{Fields.CREATED_ON}")

    @property
    def tracks_count(self) -> int:
        return self.tracks.count()
