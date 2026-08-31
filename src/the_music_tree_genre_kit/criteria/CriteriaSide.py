from django.db import models


class CriteriaSide(models.TextChoices):
    """
    Meaningful only for a genre criteria that is a root criteria's direct child
    (`parent_id == root_id`); ignored elsewhere. Unset/null means "core" -- the
    required, non-pop branch. Only exists on a genre-type criteria's concrete
    subtype: the `side` column itself lives on `AbstractGenreCriteria`, a mixin
    meant to be combined via multi-table inheritance with a consumer's concrete
    `Genre` model, so setting it on any other criteria type is now schema-enforced
    rather than validated (see `AbstractGenreCriteria._validate_side` for the
    placement/uniqueness constraints still enforced on save).
    """

    CORE = "core"
    POP = "pop"
