from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException
from the_music_tree_api_kit.exception.validation.FieldValidationErrorCode import FieldValidationErrorCode
from the_music_tree_api_kit.serializer.SerializerType import SerializerType
from the_music_tree_api_kit.view.viewset.model.AppModelViewSet import AppModelViewSet

from the_music_tree_genre_kit.criteria.AbstractCriteria import AbstractCriteria
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_import.serializer import (
    CriteriaTreeImportSerializer,
)


class AbstractCriteriaViewSet[T: AbstractCriteria](AppModelViewSet[T]):
    def get_serializer_class_for_non_standard_action(self) -> type[Serializer]:
        if self.action == "import_tree":
            return CriteriaTreeImportSerializer
        raise NotImplementedError(f"Action {self.action} not defined in viewset")

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """
        Returns a tree structure of all criteria.
        The structure follows the format:
        {
          "name": "Criteria name",
          "children": [
            {
              "name": "Child criteria name",
              "children": []
            }
          ]
        }
        """
        tree = self.model_class.objects.build_criteria_tree(request.user)
        return Response(tree, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="tree/import")
    def import_tree(self, request):
        """
        Imports a tree structure of criteria, replacing all existing criteria of the current type.
        Returns a paginated list of created criteria.
        The input should be an array of criteria trees, where each tree follows the format:
        {
          "name": "Criteria name",
          "children": [
            {
              "name": "Child criteria name",
              "children": []
            }
          ]
        }
        """
        try:
            serializer = CriteriaTreeImportSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.model_class.objects.import_criteria_tree(request.user, serializer.validated_data)
        except ValueError as e:
            raise AppValidationException(
                field_name="data", message=str(e), field_validation_error_code=FieldValidationErrorCode.FORMAT_INVALID
            )

        queryset = self.get_queryset()
        return self._get_paginated_list_response(queryset, SerializerType.SIMPLE, status.HTTP_201_CREATED)
