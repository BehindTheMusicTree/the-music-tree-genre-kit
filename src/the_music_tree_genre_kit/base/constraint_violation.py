from django.db import models


def constraint_violated(*, model: type[models.Model], error_message: str, constraint_name: str) -> bool:
    """
    Detect whether an `IntegrityError`'s message was caused by the named model constraint,
    without depending on backend-specific wording: Postgres includes the constraint name
    verbatim, but SQLite's `UNIQUE constraint failed` text instead lists the involved
    column names (e.g. "table.col1, table.col2") and never the constraint's own name.
    """
    if constraint_name in error_message:
        return True

    constraint = next((c for c in model._meta.constraints if c.name == constraint_name), None)
    if not isinstance(constraint, models.UniqueConstraint):
        return False

    columns = [model._meta.get_field(field_name).column for field_name in constraint.fields]
    return all(column in error_message for column in columns)
