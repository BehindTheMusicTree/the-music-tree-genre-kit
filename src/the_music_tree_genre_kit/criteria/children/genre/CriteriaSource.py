from django.db import models


class CriteriaSource(models.TextChoices):
    """
    Who owns a genre row. Only `PIPELINE` rows are ever deleted by
    `AbstractCriteriaManager.import_criteria_tree`'s stale pass; `APP` and `ADMIN`
    rows survive any import.
    """

    PIPELINE = "pipeline"
    APP = "app"
    ADMIN = "admin"
