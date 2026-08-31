from django.db import models


class CriteriaSide(models.TextChoices):
    """
    Meaningful only for a genre criteria that is a root criteria's direct child
    (`parent_id == root_id`); ignored elsewhere. Unset/null means "core" -- the
    required, non-pop branch. Only valid on genre-type criteria; setting it on any
    other criteria type raises on save (see `AbstractCriteria._validate_side`).
    """

    CORE = "core"
    POP = "pop"
