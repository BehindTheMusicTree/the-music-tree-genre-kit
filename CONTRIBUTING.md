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

**Important:** No direct commits to `main` or `develop` — all changes, including from maintainers, go through Pull Requests.

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

This project follows strict [Gitflow](https://nvie.com/posts/a-successful-git-branching-model/).

- **`main`** — production-ready code only. No direct commits — only merges from `release/*` and
  `hotfix/*` branches. Every merge to `main` is tagged.
- **`develop`** — integration branch, the default branch and PR target for day-to-day work. No
  direct commits — only merges from PRs.
- **`feature/<name>`** — new features, branched from `develop`, merged back into `develop` via PR.
- **`fix/<name>`** — bug fixes, branched from `develop`, merged back into `develop` via PR.
- **`chore/<name>`** — maintenance, tooling, CI/CD, dependency updates, branched from `develop`,
  merged back into `develop` via PR.
- **`release/<x.y.z>`** — release stabilization, branched from `develop`. Merged into `main`
  (then tagged) and back into `develop` when ready. Only fixes belong here, no new features.
- **`hotfix/<x.y.z>`** — urgent production fixes, branched from `main`. Merged into `main` (then
  tagged) and back into `develop`.

There is no automated branch-name enforcement — these prefixes are a convention, not a CI-checked rule.

### 3. Testing

```bash
uv run pytest
```

Also run before opening a PR — these are the same checks CI runs (`.github/workflows/test.yml`, jobs `Lint`, `Fixture makemigrations check`, `Pytest`):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
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

- ✅ `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, and `uv run pytest` all pass
- ✅ New abstractions have corresponding coverage in `tests/fixture_app/`
- ✅ `CHANGELOG.md` updated under `[Unreleased]`
- ✅ `README.md` updated if the package's scope or usage changed
- ✅ No secrets, large files, or accidental commits
- ✅ Branch targets `develop` (or `main`, for a `release/*`/`hotfix/*` branch only)

**PR title** follows the same `<type>(<scope>): <summary>` format as commits, e.g. `feat(criteria-playlist): hoist AbstractCriteriaPlaylist from grow/hear`.

### 6. Releasing (For Maintainers)

Releases follow Gitflow, tagged on `main`:

1. Branch `release/x.y.z` from `develop`.
2. Bump `version` in `pyproject.toml` and finalize the `[Unreleased]` section of `CHANGELOG.md` on
   that branch. Only bugfixes belong here — no new features.
3. Open a PR from `release/x.y.z` into `main`; once merged, tag and push:

   ```bash
   git checkout main
   git pull origin main
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

4. Merge `release/x.y.z` back into `develop` (PR) so the version bump and changelog land there
   too, then delete the release branch.
5. Pin the dependency on `the-music-tree-api-kit` to a tag, never a raw commit SHA — see the `[Unreleased]`/`v0.2.1` changelog entries below for why.
6. Consumers (`grow-the-music-tree-api`, `hear-the-music-tree-api`) re-pin their dependency on this package to the new tag.

An urgent fix to production code goes through `hotfix/x.y.z` instead: branch from `main`, fix,
PR into `main`, tag, then PR the same fix back into `develop`.

## License & Attribution

All contributions are made under the project's Apache License 2.0. You retain authorship of your code; the project retains redistribution rights under the same license. See the [LICENSE](LICENSE) file for details.
