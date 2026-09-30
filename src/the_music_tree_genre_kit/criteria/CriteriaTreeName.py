from django.db import models


class CriteriaTreeName(models.TextChoices):
    """
    Which tree a criteria belongs to. The regional tree is the one allowing multiple
    primary parents (see `AbstractCriteria.allows_multiple_primary_parents`).
    """

    CANONICAL = "canonical"
    REGIONAL = "regional"
