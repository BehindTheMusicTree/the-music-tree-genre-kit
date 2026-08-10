from django.conf import settings
from django.db import models

from the_music_tree_genre_kit.base.BaseModel import BaseModel
from the_music_tree_genre_kit.field.AppCharField import AppCharField


class CriteriaType(BaseModel):
    label = AppCharField(unique=True, max_length=settings.CRITERIA_TYPE_LABEL_LEN_MAX)

    def __str__(self) -> str:
        return f"{self.pk} | {self.label}"

    class Meta:
        app_label = "the_music_tree_genre_kit"
        constraints = [models.CheckConstraint(condition=~models.Q(label=""), name="criteria_non_empty_label")]
        verbose_name = "Criteria Type"
        verbose_name_plural = "Criteria Types"
