from tests.fixture_app.models import Criteria
from the_music_tree_genre_kit.serializer.model.criteria.output.simple import build_criteria_simple_serializer
from the_music_tree_genre_kit.view.viewset.AbstractCriteriaViewSet import AbstractCriteriaViewSet


class CriteriaViewSet(AbstractCriteriaViewSet[Criteria]):
    def __init__(self, **kwargs):
        super().__init__(
            model_class=Criteria,
            simple_serializer_class=build_criteria_simple_serializer(Criteria),
            **kwargs,
        )
