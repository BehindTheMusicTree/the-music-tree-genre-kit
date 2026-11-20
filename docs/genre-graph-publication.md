# Publishing the pure genre graph

The pure package and Django kit have separate versions and release contracts, both driven by
release-please from `main` (`release-please-config.json`, `.release-please-manifest.json`).
The pure package uses `.github/genre-graph-release-policy.json`, its own changelog
(`packages/genre-graph/CHANGELOG.md`) and `graph-vX.Y.Z` tags. The kit uses
`.github/release-policy.json`, `CHANGELOG.md` and `vX.Y.Z` tags with a GitHub Release.
Every job of `.github/workflows/release.yml` pins the same github-workflows commit.

## Setup

Configure the PyPI Trusted Publisher for `the-music-tree-genre-graph` with owner
`BehindTheMusicTree`, repository `the-music-tree-genre-kit`, workflow filename
`release.yml`, and environment `pypi`. This external setup is not verified by local
checks. No API token is used. Changes to repository environment settings go through
`github-config` under the organization's existing policy.

## Release sequence

1. Merge Conventional-Commit PRs into `main`; release-please keeps one release PR up to date
   with both packages' versions, `uv.lock` and changelogs. Only changes under
   `packages/genre-graph` bump the graph; the kit's range on it must contain its version
   (checked by the `Lint` job).
2. CI arms auto-merge on the release PR; merging it (once the required checks pass) triggers `release.yml`, which runs in order:
   `tag-graph` (tags `graph-vX.Y.Z` when the graph version is not tagged yet), `build-graph`,
   `publish-graph` (Trusted Publishing, then PyPI filename/hash verification),
   `verify-public-dependency` (installs the kit from public PyPI with the exact graph version
   declared in `packages/genre-graph/pyproject.toml`, retrying up to 660 s for the index cache),
   `tag-root` (tags `vX.Y.Z` and publishes the GitHub Release) and `release-please`.
3. A root-only release skips the graph jobs; the dependency gate still checks the declared
   graph version is installable.

The release PR is auto-merged by CI (`auto-merge: true` on the `release-please` job), so merging it is
the publication step and there is no human approval beyond the required checks. To hold a release,
disable auto-merge on the PR or close it. Never create or move tags manually.

## Recovering a partial publication

Use "Re-run failed jobs" on the `Release` run to retain the original build artifact. The pinned
helper verifies its manifest and compares remote PyPI filenames and SHA-256 hashes.
It uploads only missing files, then verifies the complete file set. A mismatch fails
and requires investigation. Do not move a tag or enable blind `skip-existing`.
Rebuilding may produce different bytes; investigate such differences before retrying.
