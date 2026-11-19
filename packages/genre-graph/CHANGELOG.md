# Changelog

## [Unreleased]

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
