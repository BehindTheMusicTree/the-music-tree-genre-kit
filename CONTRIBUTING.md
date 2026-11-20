# Contributing Guidelines

Thank you for your interest in contributing! This project is currently maintained by a solo developer, but contributions, suggestions, and improvements are welcome.

## Table of Contents

- [Contributors vs Maintainers](#contributors-vs-maintainers)
- [Development Workflow](#development-workflow)
  - [1. Environment Setup](#1-environment-setup)
  - [2. Branching](#2-branching)
  - [3. Testing](#3-testing)
  - [4. Committing](#4-committing)
  - [5. Pull Request Process](#5-pull-request-process)
  - [6. Releasing (For Maintainers)](#6-releasing-for-maintainers)
- [License & Attribution](#license--attribution)

## Contributors vs Maintainers

**Contributors** can submit bug reports and feature requests via GitHub Issues, propose changes via Pull Requests, improve documentation, and participate in discussions.

**Maintainers** review and merge Pull Requests, manage repository configuration, and are responsible for project direction.

**Important:** No direct commits to `main` — all changes, including from maintainers, go through Pull Requests.

Currently this project has a solo maintainer, but the role may expand as the project grows.

## Development Workflow

### 1. Environment Setup

#### Prerequisites

- Python 3.14
- [uv](https://docs.astral.sh/uv/)

#### Installation

```bash
git clone https://github.com/BehindTheMusicTree/the-music-tree-genre-kit.git
cd the-music-tree-genre-kit
uv sync --all-extras
```

This is an installable Python package (shared genre/tag/criteria/tree Django abstractions) consumed by `hear-the-music-tree-api` and `grow-the-music-tree-api` — not a deployable service, so there's no server to run locally. It depends on `the-music-tree-api-kit` for generic infra. New abstractions are exercised against `tests/fixture_app/`, a minimal in-repo Django app backed by SQLite.

### 2. Branching

This project follows [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow).

- **`main`** — the only long-lived branch, the default branch and PR target. No direct commits —
  only merged PRs. Every merge to `main` is validated by CI.
- **Topic branches** (`feature/<name>`, `fix/<name>`, `chore/<name>`, `ci/<name>`, …) — branched from
  `main`, merged back into `main` via PR with a Conventional-Commits title.
- **`release-please--*`** — the release PR, opened and kept up to date automatically (see Releasing).

There is no automated branch-name enforcement — these prefixes are a convention, not a CI-checked rule.

### 3. Testing

```bash
uv run pytest
```

Also run before opening a PR — these are the same checks CI runs (`.github/workflows/validate.yml`, jobs `Lint`, `Fixture makemigrations check`, `Pytest`):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src packages/genre-graph/src
uv run django-admin makemigrations fixture_app the_music_tree_genre_kit --check --dry-run
```

The last command covers both the fixture app's migrations and this package's own concrete models (e.g. `CriteriaType`) — unlike `the-music-tree-api-kit`, this package ships some concrete tables, not only abstract bases, so it carries its own migrations directory.

### 4. Committing

Structured commit format inspired by [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<scope>): <summary>
```

Types: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `style`, `perf`, `ci`.

Examples:

- `feat(criteria-playlist): hoist AbstractCriteriaPlaylist from grow/hear`
- `fix(TreeField): move logger assignment above import block`
- `chore: update dependencies`

Use imperative mood, keep the summary under ~70 characters, include issue IDs when applicable.

### 5. Pull Request Process

Before opening a PR:

- ✅ `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src packages/genre-graph/src`, and `uv run pytest` all pass
- ✅ New abstractions have corresponding coverage in `tests/fixture_app/`
- ✅ The PR title is a valid Conventional Commit (it drives the release notes; do not edit `CHANGELOG.md` by hand)
- ✅ `README.md` updated if the package's scope or usage changed
- ✅ No secrets, large files, or accidental commits
- ✅ Branch targets `main`

**PR title** follows the same `<type>(<scope>): <summary>` format as commits, e.g. `feat(criteria-playlist): hoist AbstractCriteriaPlaylist from grow/hear`.

### 6. Releasing (For Maintainers)

Releases are automated with [release-please](https://github.com/googleapis/release-please) on `main`:

1. Merging Conventional-Commit PRs into `main` makes the `Release` workflow open or update a single
   release PR. It bumps `pyproject.toml` (and `uv.lock`) and writes `CHANGELOG.md` for the kit
   (`v*` tags) and for the pure graph package (`packages/genre-graph`, `graph-v*` tags).
2. CI arms squash auto-merge on the release PR, so it merges once the required checks pass, with no
   human review (to hold a release, disable auto-merge on the PR or close it). The `Release` workflow then, in order: tags the graph, builds and
   publishes it to PyPI (Trusted Publishing, environment `pypi`), verifies that the kit installs from
   public PyPI with that exact graph version, and finally tags the kit and publishes its GitHub Release.
3. A failed job is recovered with "Re-run failed jobs"; already published files are not re-uploaded.
4. Pin the dependency on `the-music-tree-api-kit` to a tag, never a raw commit SHA — see the `v0.2.1` changelog entry for why.
5. Consumers (`grow-the-music-tree-api`, `hear-the-music-tree-api`) re-pin their dependency on this package to the new tag.

The kit's range on `the-music-tree-genre-graph` must contain the graph version (checked by the `Lint`
job). Do not create or push tags locally.

## License & Attribution

All contributions are made under the project's Apache License 2.0. You retain authorship of your code; the project retains redistribution rights under the same license. See the [LICENSE](LICENSE) file for details.
