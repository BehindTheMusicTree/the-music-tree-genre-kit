# Semantic graph v2 contract

This contract prepares the multi-parent regional plan. `GenreGraph` validates an
in-memory snapshot; `genre_graph.storage` persists it in separate Django tables,
with SQL selections. Endpoints, catalog migration and interfaces
remain to be adapted. The historical `genre_tree` contract and personal trees
keep using their current import. No producer may emit this new format before its
consumers are ready.

## Identities and relations

`contractVersion: 2`, `curationExportedOn`, `nodes`, `relations` and `canonicalRoots`
are required. An explicitly empty root list is valid; a missing
configuration fails. Identities are QIDs or persistent `LOCAL:` identities,
independent of the label and of the display parent.

| Child → parent relation | Scope | Transmission |
| --- | --- | --- |
| `classification` | Genre → genre | Canonical state; population according to the rules below |
| `regional_membership` | Regional node → overview, non-canonical genre or expression | The child's entire regional population |
| `expression_style` | Expression → style (canonical or not) | Access from the style to the expression; no reverse access |
| `anchoring` | Genre → overview | Descriptive only |

An overview can only belong to another overview. No canonical genre can be the
child or the parent of a regional membership: a population limited to a region
requires a distinct expression. An expression has at least one explicit style,
canonical or not. A classified genre (a classification parent) cannot be a
regional member: only a classification root (a genre with no classification
parent) can belong to a region. Its regional descendants belong to its population.

Relations and canonical roots carry `decisionId`, `source` and `rationale`.
`displayParentId`, when present, designates an accepted parent; it never
chooses the state or the population. Unknown references, identity or relation
duplicates, cycles and contradictions fail before a snapshot is returned.
Cycles are also checked on the unions of transmitting relations.

## Canonical roots

A genre is canonical or regional; other kinds have no state
(`GenreGraph.canonical_state`). `canonicalRoots` lists the classification roots
(genres with no classification parent) that start a canonical tree, each with its
provenance. A listed root is canonical and so is every classification descendant.
A genre that is not reached from a listed root is regional: it must reach an
overview through regional membership, otherwise the graph is rejected.

An entry that is unknown, duplicated, not a genre or that has a classification
parent is rejected. A genre whose classification parents are partly canonical and
partly regional is rejected with one witness edge per parent. The state is always
computed: a supplied `canonicalState`, `boundaries` or `isUnacceptedRoot` is
refused by the schema. The explicit empty list is valid and yields no canonical genre.

## Selections and normalization

Access is typed: from a node, any run of regional membership and classification
edges, then at most one `expression_style` jump, after which only classification
edges are followed (an expression reaches the classification ancestors of its
style, never the regions of that style). A node is selected by `n` exactly when
`n` is one of its access ancestors or `n` itself.

| Selected node / inclusive scope | Attributable node set |
| --- | --- |
| Canonical / `canonical` | Chosen genre and its classification descendants |
| Canonical / `regional` | Chosen genre, plus every other node that reaches it: expressions and their regional population |
| Canonical / `all` | Distinct union of the two scopes |
| Regional genre, overview or expression / `all` | Chosen node and everything that reaches it by typed access |

Without descendants, only the chosen node is kept. The `canonical` and
`regional` scopes are not accepted on a regional node. Selecting the United
States keeps Country and Bluegrass but not French country: the jump from
French country to Country stops at the style, so the region of the style never
reaches the expression.

`normalize_attributions` drops an attribution only when the surviving ones still
select it and everything above it. Access is not transitive, so `{USA, French
country}` keeps both while `{Country, Bluegrass}` keeps Bluegrass. The topmost
nodes are examined first, so the result does not depend on input order.
Anchorings do not make any attribution redundant. Normalization precedes the
computation of the directly attributed overviews that remain "to refine".

An expression of a regional style must live in a region disjoint from the style's
(a nested region would be a child style); an expression of any style with no
region is rejected.

A `current` overview is always umbrella. A `historical` overview is umbrella
exactly when it has an accepted regional child, regardless of its display parent
and of the number of songs. The type and its provenance are explicit. A supplied
`isUmbrella` flag that contradicts this is rejected.

Reduction applies only to `regional_membership` relations, never to
classification, anchorings or associations. `ancestry_subgraph` returns the
shared nodes and the regional population relations, including non-canonical
classification; it does not enumerate every route.

These functions work on concepts, not on catalog songs. Consumers must apply the
resulting sets and count distinct songs in SQL; summing per-attribution buckets
would be incorrect.

## Fixtures and validation

`tests/fixtures/genre_graph/regional-v2.json` is synthetic. The musical names
are not an approved curation. The canonical-root tests also cover a 1,710-node graph
with a single listed root.

`observed-additional-children.json` freezes the 44 observations of
`/tmp/regional-staging-validation/leaf-cases.json`, a diagnostic of November 13, 2026.
SHA-256: `a3496975abd53eb0fa4752c6288b860f23a22d932976e574934f39a25b8b339b`.
Each observation is replayed with a different display parent and checks the
children, the selection and the umbrella flag. The replay's roles and types are
test inputs; they validate neither real chronology nor musical inclusion.
This replay does not claim to cover the whole pipeline of the historical diagnostic.

The C/X/M/R/E IDs in test names refer to the matrix
[`genre-graph-fixture-matrix.md`](genre-graph-fixture-matrix.md). The kit's tests
cover the in-memory contract, storage and its SQL selections. The PostgreSQL
tests use a minimal application and the kit's real migrations; they check
concurrent creations, revision conflicts and the consistency of locked reads.
They are skipped under SQLite and run in a separate CI job. Catalog migration,
consumer caches, geohistorical decisions and the end-to-end replay remain open
with their owners.

## Storage, concurrency and restoration

`replace_graph(key=..., payload=..., expected_revision=...)` validates the graph
before any write. `None` requires a creation; an existing revision requires the
token re-read by the client. The replacement keeps the concepts' permanent keys,
archives the payload and applies the closure differences in the same
transaction. Each removed concept requires an explicit decision
`{target: identity | null, provenance: {decisionId, source, rationale}}`. The
concept stays archived with `is_active=False`; reactivating it reuses its key.
Attributions are remapped in SQL to the explicit target, or removed for a null
target, keeping their history and all origin, destination and removal evidence.
No track is deleted.

A track carries at most one node per dataset. `GenreGraphAttribution.dataset` is
denormalized from the node and immutable (composite foreign key
`(dataset_id, node_id)` on PostgreSQL, equivalent triggers on SQLite), and
`UNIQUE(dataset_id, track_id)` applies across the whole kit, including direct SQL
writes. `replace_track_attributions` and `restore_track_attributions` reject more
than one identity, and `publish_staged_attributions` rejects a staged set with
several nodes for the same track. Remapping a removal cannot create a duplicate:
the track had only one node, and it keeps only one, with the origin, destination
and removal evidence. Migration 0022 fails, naming the dataset and the track,
while duplicates exist; it never picks a node.

`select_tracks(tracks, *, node, scope, include_descendants)` takes the
already-loaded `GenreGraphNode` (read in the same snapshot as the result
evaluation) and issues no query at call time; an inactive node selects nothing,
and an invalid scope or a scope other than `all` on a non-canonical node raises
`GraphValidationError`. `select_tracks`, `effective_attributions` and
`tracks_needing_refinement` use SQL subqueries: they do not materialize track
populations in Python. `effective_attributions` returns the dataset's active
attributions (there is no longer any "more precise" normalization to do);
`tracks_needing_refinement` keeps the umbrella semantics. The queryset supplied
by the consumer keeps its access scope and its playability criteria. Counts use
distinct tracks, including when a node has several access paths.

To render several results with their tokens, evaluate all the querysets inside
`graph_read_snapshot()`, after authentication. Under PostgreSQL, this context
opens an outer REPEATABLE READ, READ ONLY transaction; readers can overlap and do
not block a concurrent publication. `graph_read_transaction(key=...)` also loads
the dataset in that snapshot, without `payload` (deferred); pass
`with_payload=True` to load it eagerly, and only read a deferred `payload` inside
the block. Nested read contexts share the snapshot; entering from an outer
transaction not owned by this context fails. Materialize the results before
leaving the context: a lazy queryset does not carry the snapshot.

Consumers that write attributions in bulk or delete attributed tracks must enter
`graph_write_transaction(key=..., expected_revision=...)` before locking or
modifying the tracks and their attributions. For several datasets, acquire these
contexts in key order. The attribution service already takes its locks in that
order. Triggers ensure invalidation for direct ORM/SQL writes, but cannot fix
their lock ordering: without this context, a concurrent write may be cancelled by
PostgreSQL for deadlock. The token checks the graph version; writes require
READ COMMITTED and are forbidden inside a read snapshot. Each attribution set
also has an `expected_assignment_revision`: `None` allows its first creation,
then the current token is mandatory, including after an explicit clearing. A
stale revision fails before the evidence is recorded.

`revision` identifies the graph; `membership_revision` invalidates the
populations. A graph replacement changes both. Attribution triggers change the
latter for inserts, updates and deletes, including bulk writes and cascading
track deletions. Under PostgreSQL, transition tables limit invalidation to once
per dataset and SQL statement. SQLite uses per-row triggers. A rollback cancels
the tokens along with the mutations. The concept and closure index is internal:
modifying it directly through ORM or SQL is not a graph-editing contract.
Changes to relations, canonical roots and types go through `replace_graph`.

`replace_track_attributions` requires a track with no owner, known identities, a
non-empty array of evidence per identity, the graph's current revision and the
attribution set's token. Each piece of evidence contains `decisionId`, `source`
and `rationale`. Its content is immutable within the dataset: reusing an
identifier with different content fails. An identical repetition, even with the
evidence in a different order, rewrites nothing. Previous and next states are
archived with their semantic identities and provenance, without FKs to the
concepts that may be removed. `restore_track_attributions` restores an explicit
snapshot; it refuses absent concepts and does not recreate a deleted track.
Archives and evidence refuse direct modifications and deletions. Direct ORM/SQL
mutations invalidate the tokens, but do not create the complete business
history: publications must use the services. `restore_graph` restores only the
graph: to restore both, first restore the necessary concepts, then the
attribution snapshots, in an enclosing transaction. Consumers must archive their
migration mappings and other projections separately.

## Python compatibility and installation

The Django kit requires Python 3.14. The independent package
`the-music-tree-genre-graph`, in `packages/genre-graph`, accepts Python 3.12 and
depends only on `jsonschema`. Producers import `GenreGraph`,
`GraphValidationError` and `load_genre_graph_schema` from
`the_music_tree_genre_graph`; they do not copy the Django kit's classifier. The
kit's dependency is bounded to `>=0.1.0,<0.2.0`. CI builds the wheel and the
sdist and replays the same tests outside the workspace on Python 3.12 and 3.14,
without Django. It also installs the kit's wheel and sdist with an explicit pure
wheel on Python 3.14 and replays the SQLite storage tests. These checks validate
the local artifacts, not their availability on a public index.

The workspace's uv source is not passed on to consumer projects. A Git
installation of the kit therefore needs an explicit published source for the pure
package; the development branch is not yet a deliverable dependency.
Publication and pin changes require a separate release authorization. Existing
pins remain unchanged until then.

Migration `0020` refuses a downgrade if the evidence or history storage is
populated: flattening several pieces of evidence would destroy provenance.
Application-level restoration of the graph and attributions remains a forward
operation; a physical return to the earlier schema requires a database backup
taken before migration.
