from the_music_tree_api_kit.view.viewset.model.AppModelViewSet import AppModelViewSet

from tests.fixture_app.models import Criteria, Track
from the_music_tree_genre_kit.serializer.model.criteria.output.simple import build_criteria_simple_serializer
from the_music_tree_genre_kit.view.viewset.AbstractCriteriaViewSet import AbstractCriteriaViewSet
from the_music_tree_genre_kit.view.viewset.genre.GenreExampleTreeMixin import GenreExampleTreeMixin
from the_music_tree_genre_kit.view.viewset.track.SongExampleTreeMixin import SongExampleTreeMixin


class CriteriaViewSet(AbstractCriteriaViewSet[Criteria]):
    def __init__(self, **kwargs):
        super().__init__(
            model_class=Criteria,
            simple_serializer_class=build_criteria_simple_serializer(Criteria),
            **kwargs,
        )


class GenreCriteriaViewSet(GenreExampleTreeMixin[Criteria], AbstractCriteriaViewSet[Criteria]):
    def __init__(self, **kwargs):
        super().__init__(
            model_class=Criteria,
            simple_serializer_class=build_criteria_simple_serializer(Criteria),
            **kwargs,
        )


class TrackViewSet(SongExampleTreeMixin[Track], AppModelViewSet[Track]):
    def __init__(self, **kwargs):
        super().__init__(model_class=Track, **kwargs)
