from django.db import models

from the_music_tree_genre_kit.private_standard_resource.PrivateStandardResource import PrivateStandardResource

from .Fields import Fields


class AbstractCriteriaLineageRel(PrivateStandardResource):
    """
    Owns the `degree` bookkeeping shared by every criteria lineage relation table.
    Concrete subclasses must add `descendant`/`ascendant` foreign keys (named per
    `Fields.DESCENDANT`/`Fields.ASCENDANT`) pointing at their concrete criteria model,
    since this package does not ship a concrete criteria model.
    """

    degree = models.PositiveIntegerField()

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"{Fields.DEGREE}: {self.degree}"
