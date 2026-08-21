# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## Guidelines for Contributors

- Add entries to the `[Unreleased]` section under the appropriate category: `Added`, `Changed`, `Improved`, `Deprecated`, `Removed`, `Fixed`.
- Group related changes together; write clear, user-focused descriptions rather than raw git log dumps.
- Mention tests within the related feature or fix entry — "Test" is not its own category.
- On release, move `[Unreleased]` entries into a dated `## [X.Y.Z] - YYYY-MM-DD` section and leave an empty `[Unreleased]` above it.

## [Unreleased]

### Added

- `GenreExampleTreeMixin` for the `tree/load-example` action.
- `AbstractCriteriaViewSet` shared across the `tree/import_tree` actions.
- Shared example genre tree fixture bundled with the package.
- `AbstractCriteriaPlaylist`/`AbstractCriteriaPlaylistManager`, hoisted from the near-identical `CriteriaPlaylist`/`CriteriaPlaylistManager` implementations duplicated across grow and hear. Track-touching methods (`_get_direct_tracks`, `_create_track_rel`, `_delete_track_rels_and_fill_positions`, `_get_track_rels_for_tracks`, `_move_track_rels_to_playlist_beginning`) are required-override hooks, since the two apps' track models diverge. `bootstrap_criterialess_playlists_for_user()` idempotently ensures the criteria-less catch-all playlist rows exist per `(user, type)` — fixes a `CriteriaPlaylist.DoesNotExist` crash on deleting a root `Genre`/`Tag` when those rows were never created.
- Consuming apps must set `settings.CRITERIA_MODEL` (e.g. `"grow.Criteria"`), resolved the same way Django resolves `settings.AUTH_USER_MODEL`.

## [0.2.2] - 2026-08-12

### Fixed

- Replaced abstract `Meta.model` with factory functions in criteria serializers.

## [0.2.1] - 2026-08-11

### Fixed

- Bumped the `the-music-tree-api-kit` dependency pin from a raw commit SHA to the `v0.1.0` tag — tags give a stable, auditable reference; a raw SHA pin doesn't communicate intent and can't be diffed against a changelog.

## [0.2.0] - 2026-08-11

### Changed

- Depend on `the-music-tree-api-kit` for generic infra instead of duplicating it in-package.

### Fixed

- Moved a logger assignment above the import block in `TreeField`.

## [0.1.0] - 2026-08-10

- Initial release.
