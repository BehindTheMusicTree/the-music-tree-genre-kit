---
name: code-review
description: Repository-specific context for reviewing pull requests in the-music-tree-genre-kit. Use this whenever reviewing changes to this repo's Django models, serializers, or fields.
license: MIT
---

`the-music-tree-genre-kit` is an installable Python library (uv, PEP 621), not a deployable Django project. It ships **abstract** Django model/serializer base classes for the genre/tag/criteria/tree domain, consumed by separate services (`hear-the-music-tree-api`, `grow-the-music-tree-api`) that provide their own concrete subclasses, `User` model, and settings constants (`CRITERIA_NAME_LEN_MAX`, etc.).

## Scope boundary

This repo depends on `the-music-tree-api-kit` for all generic, non-genre infrastructure (`BaseModel`, `PrivateModel`, `AppInputSerializer`, `AppValidationException`, generic `App*Field`/`Private*Field`, `uuid/`, `public_standard_resource/`, etc.). Flag any PR that:
- Adds new generic/reusable infra here instead of in api-kit (e.g. a new field type or base model with no criteria/tag/tree coupling belongs upstream, not here).
- Reintroduces a class that already exists in api-kit instead of importing it.
- Imports from `the_music_tree_genre_kit` for something that is actually api-kit's concern, or vice versa — this repo previously had these two boundaries confused and had to be split back apart (see `AbstractCriteria`/`AbstractCriteriaManager` for the correct shape: pure tree-structure logic only, no playlist/file/AFP side effects, extension points exposed as `_on_created`/`_on_parent_changed`/`_on_renamed`/`_on_before_delete` no-op hooks for consumers to override).

## Models and ownership

Read `.agents/rules/model-migrations.md`. The package ships concrete tables as well as abstract consumer-implemented models. Check the actual model and intended ownership; do not flag an existing concrete model merely for being concrete. Review hardcoded consumer references and consumer-specific side effects in abstract bases.

## Style and tooling

- Ruff config is vendored from `hear-the-music-tree-api/baselines/ruff.toml` (`line-length = 120`, `target-version = "py313"`) via `extend` in `pyproject.toml` — don't suggest reformatting to a different line length or diverging from the vendored baseline; if a rule needs a new ignore, it belongs in `pyproject.toml`'s `[tool.ruff.lint.per-file-ignores]`, not a local `# noqa` sprinkle, unless it's truly one-off.
- Deferred/local imports inside functions and methods (`PLC0415`) are allowed and used deliberately throughout `src/**` (matches hear-api's convention) — don't flag them as a style issue.
- `mypy` runs with several error codes disabled repo-wide (`abstract`, `arg-type`, `assignment`, `attr-defined`, etc. — see `[tool.mypy] disable_error_code` in `pyproject.toml`) because of Django's dynamic model/manager typing. Don't ask for stricter local `# type: ignore` cleanup that fights this; it's an intentional, repo-wide tradeoff.
- No `print()`/debug leftovers — this repo has previously had leftover debug `print()` calls land in `TreeField` and get reverted; flag any new ones.
- Fields are exposed as string-constant classes (`Fields.NAME_PUBLIC`, `Fields.PARENT`, etc.) rather than hardcoded string literals scattered through query/serializer code — flag new code that hardcodes a field name string where a `Fields` constant already exists or should be added.

## Migrations

Apply `.agents/rules/model-migrations.md` and run the documented check for both migration histories. Review schema/data compatibility; only require migration changes where Django or the actual operation needs them.

## Cross-repo dependency pins

`pyproject.toml` pins `the-music-tree-api-kit` via `git+https://...@<tag>`. When reviewing a PR that bumps this pin, confirm the tag resolves to the intended release commit on api-kit's `main` (not a feature branch) and that the corresponding api-kit change has already merged and gone green in its own CI — this repo's CI has no visibility into api-kit's own test suite, only that the pinned commit resolves and imports cleanly.
