from django.db import models


class CriteriaSide(models.TextChoices):
    """
    Meaningful only for a root criteria's direct child (`parent_id == root_id`);
    ignored elsewhere. Unset/null means "core" -- the required, non-pop branch.
    """

    CORE = "core"
    POP = "pop"
