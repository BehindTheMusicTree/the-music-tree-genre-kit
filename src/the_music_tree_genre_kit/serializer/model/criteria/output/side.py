from rest_framework import serializers


class CriteriaSideSerializerMixin:
    """
    Resolves `side` for a serializer whose `Meta.model` is the shared base `Criteria`
    table rather than the concrete `Genre` MTI subtype -- `side` only exists as a column
    on `Genre` (see `AbstractGenreCriteria`), reached from a base `Criteria` instance via
    the reverse `genre` one-to-one accessor that convention requires concrete `Genre`
    models to declare (`criteria_ptr = ... related_name="genre"`).

    Safe for non-genre criteria (e.g. `Tag`): Django's `RelatedObjectDoesNotExist`
    subclasses both `Genre.DoesNotExist` and `AttributeError`, so
    `getattr(obj, "genre", None)` returns `None` rather than raising.
    """

    side = serializers.SerializerMethodField()
    # DRF's `SerializerMetaclass` only picks up declared fields from a base class via
    # `base._declared_fields` (see `rest_framework.serializers.SerializerMetaclass`),
    # not via plain MRO attribute lookup -- since this mixin isn't itself a `Serializer`
    # subclass, it has to publish `_declared_fields` by hand for `side` to be picked up
    # by consumers that mix it in via ordinary multiple inheritance.
    _declared_fields = {"side": side}

    def get_side(self, obj) -> str | None:
        genre = getattr(obj, "genre", None)
        return genre.side if genre else None
