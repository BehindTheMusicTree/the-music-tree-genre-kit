# Project agent guidance

## What this is

Installable Python package: shared genre/tag/criteria/tree Django abstractions consumed by
`hear-the-music-tree-api` and `grow-the-music-tree-api`. Not a deployable service — there's no
server to run locally. New abstractions are exercised against `tests/fixture_app/`, a minimal
in-repo Django app backed by SQLite.

It depends on `the-music-tree-api-kit` (pinned by git tag in `pyproject.toml`) for generic
infra — base model/manager classes, private/public resource mixins, foreign key fields,
validation exceptions. Those live in that package, not here.

## Commands

```bash
uv sync --all-extras          # install
uv run pytest                 # run tests (fixture_app-backed, DJANGO_SETTINGS_MODULE=tests.settings)
uv run pytest tests/test_criteria_field.py::test_to_internal_value_returns_none_for_blank_when_allowed  # single test
# full suite on PostgreSQL (needs a disposable DB; CI job `Pytest PostgreSQL (psycopg3|psycopg2)`)
POSTGRES_TEST_DATABASE=... POSTGRES_TEST_USER=... POSTGRES_TEST_HOST=... POSTGRES_TEST_PORT=5432 uv run pytest --ds=tests.postgres_settings --no-cov --create-db
uv run ruff check .
uv run ruff format --check .
uv run mypy src
DJANGO_SETTINGS_MODULE=tests.settings PYTHONPATH=. uv run django-admin makemigrations fixture_app the_music_tree_genre_kit --check --dry-run
```

The last command must stay clean — this package ships some concrete tables (not only abstract
bases, e.g. `CriteriaType`, `TrackPlaylistRel`), so it carries its own migrations directory
alongside the fixture app's. CI (`.github/workflows/validate.yml`) runs these checks as `Lint`, `Fixture makemigrations check`
and the test jobs; the test jobs and the shared `coverage` job (merged SQLite and PostgreSQL
reports, line 85 %, branch 70 %, patch 90 %) are enforced through the `Tests success` gate.

Ruff config extends `baselines/ruff.toml` (vendored from `hear-the-music-tree-api`), with
`PLC0415` (deferred imports) allowed under `src/**` — deferred imports are used deliberately
across Django models/serializers to avoid app-loading cycles, mirroring hear-api's pattern.

## Architecture

### Abstract-first, consumer-completed

Almost everything here is an `Abstract*` Django model/manager (`abstract = True`). Consuming
services (`hear`, `grow`) provide the concrete subclasses and required settings
(`CRITERIA_MODEL`, `TRACK_MODEL`, `ARTIST_MODEL`, `ALBUM_MODEL` — enforced at startup by
`checks.py`'s `check_swappable_model_settings`, a Django system check). The package also ships concrete, migration-bearing models, including `CriteriaType`, `Track`, `TrackPlaylistRel`, `Playlist`, and `ImportRun`. Check the model and its migrations before classifying a model as abstract or concrete.

**Do not assume an abstract model has a table to query.** Per the README, things like a genre-scoped
`CriteriaField` subclass, `Criteria`-bound input serializers, or `CriteriaDetailedSerializer`
output serializers belong in the consuming service, built against its own concrete `Criteria`.
This package instead ships *builder functions* that return dicts of serializer fields (e.g.
`build_criteria_detailed_tracks_fields`, `build_criteria_playlist_minimum_serializer`) for a
consumer to assign onto its own serializer classes — a way to share field logic without
requiring a shared concrete model.

### `AbstractCriteria` — the tree

`criteria/AbstractCriteria.py` owns pure tree structure: `name`, `parent`/`root`/`ascendants`
(self-referential, `ascendants` is M2M through a required concrete `CriteriaLineageRel` model —
consumers must define one named exactly `CriteriaLineageRel` in their app, since the `through`
model is resolved by name), and `side` (`core`/`pop`, meaningful only for a root's direct
child — see `CriteriaSide.py`). Non-tree concerns (uploaded tracks, playlists) are layered in
by concrete subclasses in `hear`/`grow`, not here.

`criteria/type/CriteriaType.py` is a concrete lookup table (genre vs. tag, etc.) shared by all
criteria. `criteria/children/genre/` and `criteria/children/tag/` hold manager subclasses
scoped to those criteria types.

`criteria/playlist/` (`AbstractCriteriaPlaylist`) and `criteria/track_playlist_rel/`
(`TrackPlaylistRel`, concrete) model playlists built from criteria selections, separate from
`playlist/Playlist` (concrete, manually-curated playlists) and `manual_playlist/` (abstract
manual-playlist behavior).

### Serializer builders

`serializer/model/criteria/{input,output,playlist}/` and `serializer/field/` hold reusable DRF
field/serializer pieces: `CriteriaField` (a queryset-scoped PrimaryKeyRelatedField-style field
that always requires an explicit `queryset` — see its docstring for why),
`DescendantAwareField`, `TreeField`, and output builders like `simple.py` /
`detailed_tracks.py` / `minimum.py`. These are assembled by consumers into their own serializer
classes; this package does not define full serializers that hit a concrete `Criteria` table.

### Gold genre-tree contract

`schemas/genre_tree.schema.json` is the contract of the tree import (`CriteriaTreeImportSerializer` / `CriteriaTreeNodeSerializer`) and is owned here. `curationExportedOn` is popped by grow's import, not by these serializers. Schema changes ship in a release before grow bumps and before pipelines updates its vendored copy.

## Contributing conventions (see CONTRIBUTING.md for full detail)

- GitHub Flow. No direct commits to `main` — everything goes through a PR. Topic branches
  (`feature/`, `fix/`, `chore/`, `ci/`) are cut from `main` and merged back into `main`.
- Commit/PR title format: `<type>(<scope>): <summary>` (Conventional-Commits-inspired; types:
  `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `style`, `perf`, `ci`).
- Do not edit `CHANGELOG.md` or versions by hand: release-please builds them from Conventional-Commit
  PR titles. Update `README.md` if the package's scope or usage changes.
- Releases come from the release-please PR on `main` (`.github/workflows/release.yml`), which CI
  auto-merges once the required checks pass (no confirmation step); the graph
  package is published to PyPI first, then the kit is tagged. `the-music-tree-api-kit`
  must always be pinned by tag, never a raw commit SHA (see pyproject.toml comment and changelog
  for why — `uv`'s git-ref resolution conflicts across repos otherwise).

## Scoped project rules

Before working on `src/the_music_tree_genre_kit/**/*.py` or `tests/fixture_app/**/*.py`, read `.agents/rules/model-migrations.md`. Claude `paths:` metadata is not a Codex loader. Graphify may be used when installed and useful.

## Domain glossary

`Track` here is the generic supertype of every app's concrete track model (grow `Song`, hear `UploadedTrack`); "recording" only ever means the MusicBrainz entity. Consult consumer documentation for app-specific terminology.
