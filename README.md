# the-music-tree-genre-kit

[![Test](https://github.com/BehindTheMusicTree/the-music-tree-genre-kit/actions/workflows/test.yml/badge.svg)](https://github.com/BehindTheMusicTree/the-music-tree-genre-kit/actions/workflows/test.yml)

Shared genre/tag/criteria/tree library for `hear-the-music-tree-api` and `grow-the-music-tree-api`. Installable Python package (Django abstract base classes, managers, serializer fields) — not a deployable service.

## Not shipped: consumer-defined criteria querysets

This package has no concrete, queryable `Criteria` model — only `AbstractCriteria` (`abstract = True`). Serializers/fields that need to *query* a criteria table (as opposed to just representing one) can't be shipped here, since an abstract model has no table to query. Each consuming service defines its own concrete `Criteria(AbstractCriteria)` subclass and builds these locally against it:

- **A genre-scoped field analogous to `GenreField`**: a `CriteriaField` subclass that defaults `queryset` to `Genre.objects.all()` for your local concrete `Genre` model.
  ```python
  class GenreField(CriteriaField):
      def __init__(self, input_types: list[CriteriaFieldInputType], **kwargs):
          super().__init__(queryset=Genre.objects.all(), input_types=input_types, **kwargs)
  ```
- **Input serializers analogous to hear-api's `criteria/input/post.py` and `put.py`**: these bind a `DescendantAwareField(queryset=Criteria.objects.all())` and a `UniquePerUserNameField(model=Criteria)` against your local concrete `Criteria` model.
- **`CriteriaDetailedSerializer`-style output serializers that embed domain data** (e.g. uploaded tracks, playlists): these belong entirely in the consuming service, since that data isn't part of this package's scope.

`CriteriaField` itself (shipped here) always requires an explicit `queryset` argument for this reason — see its docstring.
