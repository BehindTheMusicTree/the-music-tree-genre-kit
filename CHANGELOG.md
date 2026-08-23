# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## Guidelines for Contributors

- Add entries to the `[Unreleased]` section under the appropriate category: `Added`, `Changed`, `Improved`, `Deprecated`, `Removed`, `Fixed`.
- Group related changes together; write clear, user-focused descriptions rather than raw git log dumps.
- Mention tests within the related feature or fix entry — "Test" is not its own category.
- On release, move `[Unreleased]` entries into a dated `## [X.Y.Z] - YYYY-MM-DD` section and leave an empty `[Unreleased]` above it.

## [Unreleased]

## [0.7.1] - 2026-08-24

### Changed

- Repin `the-music-tree-api-kit` to `v0.3.0`, which includes the shared `HostValidationMiddleware`.

## [0.7.0] - 2026-08-22

### Added

- Concrete `TrackPlaylistRel` model and `TrackPlaylistRelManager` (`the_music_tree_genre_kit.criteria.track_playlist_rel`), `AbstractTrackPlaylistRel`'s first real subclass, mirroring how `Track`/`Playlist` became kit-owned in `v0.5.0`/`v0.6.0`. `TRACK_PLAYLIST_REL_MODEL` is dropped from `checks.py`'s required-settings validation and from every place the kit read it as a setting (`PlaylistManager.py`, `AbstractTrackManager.py`); the kit now hardcodes its own concrete model instead, same as it now hardcodes `Playlist`.
- `Track.playlists`, a real `PrivateManyToManyField(Playlist, through=TrackPlaylistRel)`. This is now possible because the through model is kit-owned, removing the cross-app migration cycle that forced its removal in `v0.6.0`.
- `tests/fixture_app` re-points its `TrackPlaylistRel` FKs at the kit's new concrete model and drops its own local `TrackPlaylistRel`/`TrackPlaylistRelManager`.

### Changed

- **Breaking:** consuming apps must drop their own `TrackPlaylistRel` model and `TRACK_PLAYLIST_REL_MODEL` setting; playlist-membership rows now live in the kit's own `the_music_tree_genre_kit_track_playlist_rel` table.

## [0.6.1] - 2026-08-22

### Added

- `pytest-cov`/`coverage.py` wired into the dev dependencies and test config (`fail_under = 85`, `show_missing = true`), plus new tests across `tests/test_track_manager.py`, `tests/test_playlist.py`, `tests/test_playlist_manager.py`, `tests/test_criteria_field.py`, `tests/test_descendant_aware_field.py`, and `tests/test_tree_node_serializer.py`, raising total statement coverage from ~78% to ~85%.

### Fixed

- `PlaylistTypesLabel` imported a class named `ManualPlaylistTypeLabel` that doesn't exist in that module (only `VALUE` does), breaking every import chain that touches `PlaylistTypesLabel` since the `v0.6.0` playlist hoist.
- Documented (via a regression test, not a code fix — out of scope for this test-only change) a latent bug in `AbstractTrackManager.delete_instance`: it reads `instance.playlists_with_positions`, an attribute no model or mixin in this stack defines, so the method always raises `AttributeError`. Real deletion logic lives in and works via `delete_instance_with_checking_album_and_artists_potential_deletion`, which callers should use directly until `delete_instance` itself is fixed.

## [0.6.0] - 2026-08-22

### Added

- Concrete `Playlist` model and `PlaylistManager` (`the_music_tree_genre_kit.playlist`), built via Django multi-table inheritance exactly like `Track` in `v0.5.0`, so `grow-the-music-tree-api`'s and `hear-the-music-tree-api`'s near-identical `Playlist`/`ManualPlaylist`/`PlaylistManager` no longer need to be duplicated per app. `ManualPlaylist`/`CriteriaPlaylist` become true MTI children of the kit's `Playlist` in each app, mirroring `YoutubeTrack`/`UploadedTrack`'s relationship to the kit's `Track`.
- `AbstractManualPlaylist` (`the_music_tree_genre_kit.manual_playlist`), a pure mixin (not extending `Playlist`) providing the `_name`/non-empty-name constraint/`name`/`type_label` logic shared by every app's manual playlist, mirroring `AbstractCriteriaPlaylist`'s existing shape.
- `TrackMixin`/`TrackMixinManager`/`TrackMixinWithInternalNameManager` (`the_music_tree_genre_kit.track_mixin`), hoisted so the kit's own `Playlist` (and any app's `Criteria`/`Album`/`Artist`) can share one canonical implementation instead of each app carrying its own copy.
- `AbstractTrackPlaylistRel.playlist`/`.track` now resolve to the kit's own concrete `Playlist`/`Track` directly (`"the_music_tree_genre_kit.Playlist"`/`.Track"`) instead of a per-app `PLAYLIST_MODEL` setting, since a single shared physical table needs no app-specific configuration. `PLAYLIST_MODEL` is dropped from `checks.py`'s required-settings validation.
- `tests/fixture_app` proves the abstraction in-kit: adds `ManualPlaylist`, and re-points `CriteriaPlaylist` as an MTI child of the kit's `Playlist`, alongside the existing `Track`/`Album`/`Artist` fixture coverage.

### Fixed

- Removed `Track.playlists`, the M2M-through field added in `v0.5.0` (`through=settings.TRACK_PLAYLIST_REL_MODEL`). It was purely declarative — never queried anywhere; all playlist-membership logic already goes through `TRACK_PLAYLIST_REL_MODEL` directly — and structurally broke `makemigrations` for any consuming app: `swappable_dependency` requires the through model to live in that app's first migration, but the rel model also FKs the kit's `Track`, which in turn needs that same app's `ARTIST_MODEL`/`ALBUM_MODEL`/`CRITERIA_MODEL` from its first migration, an unresolvable cycle. Confirmed via `tests/fixture_app`, whose squashed initial migration hit exactly this `CircularDependencyError`; fixed there by also splitting the fixture's `Track`/`TrackPlaylistRel` creation into a second migration after the swappable models, mirroring `grow-the-music-tree-api`'s real migration history.

## [0.5.0] - 2026-08-21

### Added

- Shared `Track` model and `AbstractTrackManager` (`the_music_tree_genre_kit.track`), built via Django multi-table inheritance so `grow-the-music-tree-api`'s and `hear-the-music-tree-api`'s near-identical `Track`/`UploadedTrack` managers can subclass a single concrete implementation instead of duplicating genre-playlist add/remove/update and album/artist orphan-cleanup logic. `Track.artists`/`.album`/`.playlists` resolve via new `ARTIST_MODEL`/`ALBUM_MODEL` swappable settings (same mechanism as the existing `CRITERIA_MODEL`/`TRACK_MODEL`/`PLAYLIST_MODEL`), validated by `checks.py`. `AbstractTrackManager.criteria_playlist_model` is a plain class attribute wired by the concrete app's manager module, mirroring the existing `lineage_rel_model`/`track_playlist_rel_model`/`track_model` precedent.
- `tests/fixture_app` proves the abstraction in-kit: its `Track` is now an MTI child of the kit's `Track`, alongside new `Album`/`Artist`/`Playlist`/`CriteriaPlaylist`/`TrackPlaylistRel` fixture models exercising the full manager end-to-end.

## [0.4.0] - 2026-08-21

### Added

- `AbstractCriteriaManager._on_before_delete` is now fully concrete (root-criteria direct-track transfer to the criteria-less playlist, tagged-track genre clearing, child reparenting), built on the sibling `AbstractCriteriaPlaylistManager` reached via `instance.criteria_playlist`. Fixes a latent bug hoisted out of grow-the-music-tree-api: the app-level `_on_before_delete` implementations used a `Genre`-specific FK-leaf relation as "direct tracks", which is always empty for non-leaf-FK criteria types like `Tag`, silently orphaning directly-tagged tracks on root deletion instead of moving them to the criteria-less playlist. `_get_direct_tracks` is now a concrete, overridable default (generic `TrackPlaylistRel`-based; override for criteria types whose leaf FK propagates rows to ancestor playlists, e.g. `Genre`). App-specific side effects (e.g. file-metadata sync) are now a new `_on_track_genre_cleared(track)` hook.
- `AbstractCriteriaPlaylistManager._get_direct_tracks` renamed to the public `get_direct_tracks`, since `AbstractCriteriaManager` now calls it directly.

### Changed

- `tests/fixture_app`'s `Track` model gained a `genre` FK to `Criteria`, to exercise the new concrete `_on_before_delete` in-kit.

## [0.3.0] - 2026-08-21

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
