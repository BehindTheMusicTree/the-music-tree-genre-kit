from django.db import connections, models


def bulk_create_mti(instances: list[models.Model], *, using: str) -> None:
    """
    Bulk-inserts already-built, already-PK'd model instances, one raw INSERT per
    concrete table level (base table first). Works around Django's
    `QuerySet.bulk_create` unconditionally refusing any model with concrete
    (multi-table-inherited) parents -- that restriction exists because an
    autoincrement child row can't normally get a PK before its parent row is
    inserted, which doesn't apply here since every instance already carries its
    final PK (a client-generated UUID) before this is called.

    Every instance must be of the same concrete model, and must already have
    its primary key -- and, for an MTI model, the inherited base-table PK
    field(s) -- explicitly set to matching values: they are distinct Python
    attributes per table level and are not synced by plain construction (e.g.
    constructing a `Genre()` independently defaults its inherited `uuid`
    attribute and its own `criteria_ptr_id` pk attribute to two different
    values).
    """
    if not instances:
        return

    model = type(instances[0])
    for level_model in _base_first_concrete_chain(model):
        _raw_insert_level(level_model, instances, using=using)


def _base_first_concrete_chain(model: type[models.Model]) -> list[type[models.Model]]:
    chain = [model]
    current = model
    while current._meta.parents:
        (parent,) = current._meta.parents.keys()
        chain.append(parent)
        current = parent
    return list(reversed(chain))


def _raw_insert_level(level_model: type[models.Model], instances: list[models.Model], *, using: str) -> None:
    connection = connections[using]
    fields = level_model._meta.local_fields
    quote = connection.ops.quote_name
    columns = ", ".join(quote(field.column) for field in fields)
    placeholders = ", ".join(["%s"] * len(fields))
    sql = f"INSERT INTO {quote(level_model._meta.db_table)} ({columns}) VALUES ({placeholders})"

    rows = [
        tuple(field.get_db_prep_save(field.pre_save(instance, True), connection) for field in fields)
        for instance in instances
    ]

    with connection.cursor() as cursor:
        cursor.executemany(sql, rows)
