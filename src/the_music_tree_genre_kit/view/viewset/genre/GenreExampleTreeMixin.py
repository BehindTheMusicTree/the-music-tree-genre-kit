import json
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from the_music_tree_genre_kit.criteria.AbstractCriteria import AbstractCriteria
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_import.serializer import (
    CriteriaTreeImportSerializer,
)


class GenreExampleTreeMixin[T: AbstractCriteria]:
    """
    Adds a `tree/load-example` action, seeding the current user's genre tree from a
    JSON fixture the consuming app ships under `settings.DATA_DIR`. Mix into an
    `AbstractCriteriaViewSet[T]` subclass for a genre viewset (not every criteria
    type has an example tree, so this isn't folded into `AbstractCriteriaViewSet`
    itself).
    """

    model_class: type[T]
    example_tree_filename: str = "genre_example_tree.json"

    def get_example_tree_data_path(self) -> Path:
        return settings.DATA_DIR / self.example_tree_filename

    def on_example_tree_loaded(self, request) -> None:
        """Hook for app-specific side effects after the example tree is imported."""

    @action(detail=False, methods=["post"], url_path="tree/load-example")
    def load_example_tree(self, request):
        data_path = self.get_example_tree_data_path()

        if not data_path.exists():
            raise FileNotFoundError(f"Example genre tree file not found at {data_path}")

        with open(data_path) as f:
            data = json.load(f)

        serializer = CriteriaTreeImportSerializer(data={"tree": data["tree"]})
        serializer.is_valid(raise_exception=True)

        self.model_class.objects.import_criteria_tree(request.user, serializer.validated_data)
        self.on_example_tree_loaded(request)

        return Response({"message": "Example genre tree loaded successfully"}, status=status.HTTP_201_CREATED)
