# Publishing the pure genre graph

The pure package and Django kit have separate versions and release contracts.
The pure package uses `.github/genre-graph-release-policy.json`, its own changelog,
and `graph-vX.Y.Z` tags. The kit retains its existing `vX.Y.Z` GitHub release policy.
The pure package caller pins github-workflows v5.3.0 at
`985268a5f321535b1ced65a16850a0453471faae`.

## Setup before the first publication

Configure the PyPI Trusted Publisher for `the-music-tree-genre-graph` with owner
`BehindTheMusicTree`, repository `the-music-tree-genre-kit`, workflow filename
`release-graph.yml`, and environment `pypi`. This external setup has not been
verified by local checks. No API token is used. Changes to repository environment
settings go through `github-config` under the organization's existing policy.

## Approved release sequence

1. Obtain release approval for the concrete package versions and publication effects.
2. Finalize the pure package's version and move its Unreleased notes into a dated
   version section. For the staged first version, keep `0.1.0`; do not bump it twice.
   Merge through the repository's release process onto `main`.
3. Create the approved immutable `graph-vX.Y.Z` tag on that merged `main` commit.
   The existing automatic kit tag workflow reads only the root policy; it does not
   create pure package tags. The pure publication policy is independently validated
   by `release-graph.yml` against the tag commit and its ancestry on `main`.
4. Wait for the pure package's build, Trusted Publishing and final PyPI filename/hash
   verification to succeed. This flow publishes to PyPI without a separate GitHub Release.
5. Proceed with the separately approved kit release. Before its GitHub Release is
   created, `release.yml` installs the kit with public dependencies and requires the
   pure package version recorded in `packages/genre-graph/pyproject.toml`.

For the initial coordinated release, merging the kit release branch onto `main`
may automatically create its kit tag before the pure tag is created. The kit's
public dependency gate then fails until the pure publication completes. Once
step 4 succeeds, rerun the failed kit release jobs; keep the existing immutable
kit tag. A blocked first attempt does not require another version bump.

Policy activation, workflow adoption and local distribution tests do not authorize
release tags, version changes, publishing, or consumer pin updates. The first pure
version remains staged until the approved release supplies its versioned notes.

## Recovering a partial publication

Rerun the failed publication job to retain the original build artifact. The pinned
helper verifies its manifest and compares remote PyPI filenames and SHA-256 hashes.
It uploads only missing files, then verifies the complete file set. A mismatch fails
and requires investigation. Do not move a tag or enable blind `skip-existing`.
Rebuilding may produce different bytes; investigate such differences before retrying.
