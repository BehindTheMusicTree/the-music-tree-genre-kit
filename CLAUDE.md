# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
uv run pytest tests/test_criteria_field.py::test_name  # single test
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run django-admin makemigrations fixture_app the_music_tree_genre_kit --check --dry-run
```

The last command must stay clean — this package ships some concrete tables (not only abstract
bases, e.g. `CriteriaType`, `TrackPlaylistRel`), so it carries its own migrations directory
alongside the fixture app's. These are exactly the checks CI runs (`.github/workflows/test.yml`:
`Lint`, `Fixture makemigrations check`, `Pytest`).

Ruff config extends `baselines/ruff.toml` (vendored from `hear-the-music-tree-api`), with
`PLC0415` (deferred imports) allowed under `src/**` — deferred imports are used deliberately
across Django models/serializers to avoid app-loading cycles, mirroring hear-api's pattern.

## Architecture

### Abstract-first, consumer-completed

Almost everything here is an `Abstract*` Django model/manager (`abstract = True`). Consuming
services (`hear`, `grow`) provide the concrete subclasses and required settings
(`CRITERIA_MODEL`, `TRACK_MODEL`, `ARTIST_MODEL`, `ALBUM_MODEL` — enforced at startup by
`checks.py`'s `check_swappable_model_settings`, a Django system check). `Track`,
`TrackPlaylistRel`, and `Playlist` are the exceptions: fully concrete and kit-owned (not
swappable), because their cross-app FK relationships created migration cycles when each
consumer defined its own.

**Do not add concrete, queryable-by-consumers logic here that requires a real table** — an
abstract model has no table to query. Per the README, things like a genre-scoped
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

### Example-data loading mechanisms

Two parallel "load example data for a user" mechanisms, both wiping the user's existing rows
and reseeding from a bundled JSON fixture in `data/`:

- `view/viewset/genre/GenreExampleTreeMixin.py` + `data/genre_example_tree.json` — loads an
  example criteria tree.
- `view/viewset/track/SongExampleTreeMixin.py` + `AbstractTrackManager.import_example_songs` +
  `data/song_example.json` — loads example tracks, matching each entry's `genre_name`
  case-insensitively against the user's own criteria (unmatched entries are skipped rather than
  creating a genre-less track).

Both are opt-in mixins for a consumer's viewset, not automatically wired up.

## Contributing conventions (see CONTRIBUTING.md for full detail)

- No direct commits to `main` — everything goes through a PR from a `feature/`, `fix/`, or
  `chore/` branch.
- Commit/PR title format: `<type>(<scope>): <summary>` (Conventional-Commits-inspired; types:
  `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `style`, `perf`, `ci`).
- Update `CHANGELOG.md` under `[Unreleased]` for any notable change, and `README.md` if the
  package's scope or usage changes.
- Releases are plain git tags on `main` (no release branch); `the-music-tree-api-kit` must
  always be pinned by tag, never a raw commit SHA (see pyproject.toml comment and changelog for
  why — `uv`'s git-ref resolution conflicts across repos otherwise).
