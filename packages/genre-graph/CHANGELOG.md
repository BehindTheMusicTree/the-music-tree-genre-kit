# Changelog

## [0.4.0](https://github.com/BehindTheMusicTree/the-music-tree-genre-kit/compare/graph-v0.3.0...graph-v0.4.0) (2026-11-21)


### Features

* **genre-graph:** add derivation relation and contract 3 ([#319](https://github.com/BehindTheMusicTree/the-music-tree-genre-kit/issues/319)) ([cfc8f97](https://github.com/BehindTheMusicTree/the-music-tree-genre-kit/commit/cfc8f97110d5e8f600632f36d37df2d7fc2fe3ea))

## [Unreleased]

## [0.3.0] - 2026-11-20

### Breaking

- `boundaries`, `canonicalState` and `isUnacceptedRoot` are removed from the schema; `canonicalRoots` is required. `GenreGraph.canonical_state` returns `canonical` or `regional` for genres. `boundary_results`, `boundary_witness` and `evaluate_boundaries` are gone (`boundaries.py` is now `validation.py`).
- Scopes follow typed access (one expression-to-style jump, then classification only); `normalize_attributions` is order independent and exact.
- A genre expression that shares every region with its regional style is now rejected.

### Added

- `GenreGraph.merged(source, target, provenance)`.

## [0.2.0] - 2026-11-20

### Added

- Expressions of non-canonical styles (`before_entry` and `after_exit`): `expression_style` accepts any genre, and selecting a non-canonical style (or a region) now includes its expressions and their regional population.

### Breaking

- A classified genre (one with a classification parent) can no longer be a regional member; only classification roots can. Use an expression instead.
- The "Expression style must be canonical" validation is removed.

## [0.1.0] - 2026-11-15

### Added

- Pure Python genre graph validation, canonical boundaries, regional memberships,
  scoped expressions, attribution normalization and the bundled graph schema.
