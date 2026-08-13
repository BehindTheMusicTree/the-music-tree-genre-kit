from django.db import models

from tests.fixture_app.manager import CriteriaManager
from the_music_tree_genre_kit.criteria.AbstractCriteria import AbstractCriteria
from the_music_tree_genre_kit.criteria.Fields import Fields as CriteriaFields
from the_music_tree_genre_kit.criteria.lineage_rel.AbstractCriteriaLineageRel import AbstractCriteriaLineageRel


class Criteria(AbstractCriteria):
    objects: CriteriaManager = CriteriaManager()

    class Meta:
        app_label = "fixture_app"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(**{f"{CriteriaFields.NAME_INTERNAL}": ""}), name="non_empty_name"
            ),
            models.UniqueConstraint(fields=[CriteriaFields.NAME_INTERNAL, "user"], name="unique_name_per_user"),
        ]


class CriteriaLineageRel(AbstractCriteriaLineageRel):
    descendant = models.ForeignKey(Criteria, on_delete=models.CASCADE, related_name=CriteriaFields.ASCENDANTS_RELS)
    ascendant = models.ForeignKey(Criteria, on_delete=models.CASCADE, related_name=CriteriaFields.DESCENDANTS_RELS)

    class Meta:
        app_label = "fixture_app"


CriteriaManager.lineage_rel_model = CriteriaLineageRel
