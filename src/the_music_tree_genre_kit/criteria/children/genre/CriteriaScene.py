from django.db import models


class CriteriaScene(models.TextChoices):
    """
    Marks a genre that is the commercial or the underground branch of its parent, so a client can render
    the two specially. Set on the branch node only, never inherited by its descendants.
    """

    COMMERCIAL = "commercial"
    UNDERGROUND = "underground"
