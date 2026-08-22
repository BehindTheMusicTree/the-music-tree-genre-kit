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
    @abstractmethod
    def tracks_not_archived(self) -> models.QuerySet[Track]:
        return self.tracks.filter(archived=False)

    @property
    def tracks_not_archived_sorted(self) -> models.QuerySet[Track]:
        return self.tracks_not_archived.order_by(f"-{Fields.CREATED_ON}")

    @property
    def tracks_not_archived_count(self) -> int:
        return self.tracks_not_archived.count()

    @property
    def tracks_archived_count(self) -> int:
        return self.tracks.filter(archived=True).count()
