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
- `AbstractCriteriaPlaylist`/`AbstractCriteriaPlaylistManager` and `AbstractTrackPlaylistRel`/`AbstractTrackPlaylistRelManager`, hoisting the near-100%-duplicated `CriteriaPlaylist`/`TrackPlaylistRel` logic out of grow-the-music-tree-api and hear-the-music-tree-api. The manager is fully concrete — no required-override hooks — via `track_playlist_rel_model`/`track_model` class attributes wired by the consuming app, mirroring the existing `AbstractCriteriaManager.lineage_rel_model` pattern. Consuming apps must set `settings.CRITERIA_MODEL`/`settings.TRACK_MODEL`/`settings.PLAYLIST_MODEL`, validated by a new Django system check.
- `bootstrap_criterialess_playlists_for_user()`, an idempotent helper that ensures the criteria-less catch-all `CriteriaPlaylist` rows exist for a user — fixes `CriteriaPlaylist.DoesNotExist` when deleting a root `Genre`/`Tag` in apps that never created these rows.

### Changed

- Bumped the `the-music-tree-api-kit` dependency pin to `v0.2.0`.

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
