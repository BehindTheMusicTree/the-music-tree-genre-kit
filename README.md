# the-music-tree-genre-kit

[![Test](https://github.com/BehindTheMusicTree/the-music-tree-genre-kit/actions/workflows/test.yml/badge.svg)](https://github.com/BehindTheMusicTree/the-music-tree-genre-kit/actions/workflows/test.yml)

Shared genre/tag/criteria/tree library for `hear-the-music-tree-api` and `grow-the-music-tree-api`. Installable Python package (Django abstract base classes, managers, serializer fields) — not a deployable service.

## Multiple parents

A criteria (genre or tag) has a main `parent` plus optional `additional_primary_parents` (only when `tree_name` is `regional`, see `CriteriaTreeName`) and `secondary_parents` (always allowed). Tracks flow up through primary parents only; secondary parents are classification links. The tree import/export (`tree/import`, `tree/`) handles one `tree_name` at a time (required `tree_name` body field on import, `treeName` query parameter on export; the manager's `import_criteria_trees` imports several trees in one transaction, which is what lets a genre move between trees keeping its pk and songs): import the `global` tree first, then the `regional` tree (the one allowing multiple primary parents), whose nodes reference the first via `primaryParents` / `secondaryParents` (wikidata id or name). A global row can only get a regional secondary parent from the regional import's optional `crossTreeSecondaryParents` list (`[{"id": ref, "secondaryParents": [refs]}]`).

## Not shipped: consumer-defined criteria querysets

This package has no concrete, queryable `Criteria` model — only `AbstractCriteria` (`abstract = True`). Serializers/fields that need to *query* a criteria table (as opposed to just representing one) can't be shipped here, since an abstract model has no table to query. Each consuming service defines its own concrete `Criteria(AbstractCriteria)` subclass and builds these locally against it:

- **A genre-scoped field analogous to `GenreField`**: a `CriteriaField` subclass that defaults `queryset` to `Genre.objects.all()` for your local concrete `Genre` model.
  ```python
  class GenreField(CriteriaField):
      def __init__(self, input_types: list[CriteriaFieldInputType], **kwargs):
          super().__init__(queryset=Genre.objects.all(), input_types=input_types, **kwargs)
  ```
- **Input serializers analogous to hear-api's `criteria/input/post.py` and `put.py`**: these bind a `DescendantAwareField(queryset=Criteria.objects.all())` and a `UniquePerUserNameField(model=Criteria)` against your local concrete `Criteria` model.
- **`CriteriaDetailedSerializer`-style output serializers that embed domain data** (e.g. uploaded tracks, playlists): these belong entirely in the consuming service, since that data isn't part of this package's scope.

`CriteriaField` itself (shipped here) always requires an explicit `queryset` argument for this reason — see its docstring.

### Genre coverage primitives

`criteria.selection.coverage` parses `genre_only` and `genre_and_subgenres` (omitted coverage is inclusive). `criteria_selection_predicate()` accepts a concrete, scoped criteria queryset and returns a predicate for a track queryset, or for playlist relations by passing `criteria_field="track__genre_id"`. The inclusive selection uses the materialized primary lineage; secondary links do not contribute. A `None` criteria ID selects only genreless tracks for either coverage. Scope the track and criteria querysets to the owner and population in the consuming service. For a catalogue request, pass `criteria_selected=False` to `parse_coverage()` when no genre parameter was supplied so explicit coverage is rejected; a selected genreless value is distinct from an absent selection.

`CriteriaCoverageCounts` validates a prepared pair. `CriteriaCoverageCountsSerializer` projects that pair, and `build_criteria_playlist_summary_serializer()` adds it to a playlist identity using `genre_only_tracks_count` and `genre_and_subgenres_tracks_count` attributes supplied by consumer annotations or prepared projections. These serializers never count per instance. The minimum playlist serializer remains identity-only. Consumers decide the catalogue and playlist populations, calculate counts before pagination or anchors, and apply selection to the playlist action's `get_track_playlist_rel_queryset()` hook before region eligibility, anchoring and pagination. The existing paginated response total after a `from` anchor describes the remaining rows, not the full selected population.

## Gold genre-tree contract

This package owns the JSON Schema of the Gold genre-tree export (`src/the_music_tree_genre_kit/schemas/genre_tree.schema.json`, loaded with `load_genre_tree_schema()`). Consumers read it from the installed package; the producer vendors a copy pinned to a release tag.

The separate [semantic graph v2 contract](docs/genre-graph-v2.md) provides a strict
schema and in-memory `GenreGraph` validation, global-root evaluation, node merging,
scoped expression selections, attribution normalization and regional ancestry.
The pure implementation lives in `packages/genre-graph` as `the-music-tree-genre-graph`
(Python 3.12+, jsonschema only). Import `GenreGraph`, `GraphValidationError` and
`load_genre_graph_schema` from `the_music_tree_genre_graph`. The Django package depends on it
with the constraint `>=0.1.0,<0.2.0`, resolved locally through the uv workspace.
Local consumers must explicitly provide both package paths; a uv
workspace source override is local to this repository and is not inherited by Git consumers.
The extracted package is released independently on PyPI; consumers can update their kit pins after publication. CI tests the pure wheel and sdist on Python 3.12 and 3.14, plus kit wheel/sdist
installation with the explicit pure wheel on Python 3.14. Reproduce with `uv build
--package the-music-tree-genre-graph --out-dir dist/genre-graph`, `uv build
--package the-music-tree-genre-kit --out-dir dist/kit` and
`bash scripts/check-graph-distributions.sh 3.14` (or `3.12` for the pure package).

Django storage supports atomic graph replacement, archived revisions, explicit reference-track
attributions and SQL distinct selections. PostgreSQL tests exercise revision conflicts,
overlapping read-only REPEATABLE READ snapshots and transactional invalidation, including
bulk writes and deletion cascades. Readers may overlap committed publications without mixing revisions. Use `graph_read_snapshot()` around response reads after authentication; `graph_read_transaction(key=...)` additionally loads a dataset in that snapshot, with `payload` deferred; pass `with_payload=True` to load it up front, and read a deferred `payload` only inside the block. PostgreSQL snapshots must be outermost, read-only transactions.

Graph nodes retain their identity after retirement. Each removed identity requires an explicit
`{target: identity | null, provenance: {decisionId, source, rationale}}` decision. Publication
archives complete assignment sets, remaps in SQL, and unions original, destination and retirement
evidence atomically. Closure replacement stages and diffs dataset-owned rows rather than rewriting
unchanged rows. PostgreSQL staging uses COPY and ANALYZE; SQLite is supported explicitly.

`replace_track_attributions` accepts `{identity: [evidence, ...]}`, an `expected_revision`
graph token and an `expected_assignment_revision` token. `None` creates a song's first assignment
set; the returned UUID reviews subsequent edits, including edits after an explicit clear. Decisions
are immutable per dataset: reusing a decision ID with different source/rationale fails. Assignment
restoration requires both reviewed tokens, an existing ownerless track, and active identities.
Direct SQL mutations invalidate assignment and membership tokens. Audit and evidence rows reject
updates and deletes. The evidence migration preserves historical decisions and fails on conflicting
legacy evidence; populated evidence storage cannot be downgraded to singular provenance.
API import endpoints and catalogue migrations are still being adapted; the legacy tree
contract remains separate. See the contract for concurrency and restoration requirements.
