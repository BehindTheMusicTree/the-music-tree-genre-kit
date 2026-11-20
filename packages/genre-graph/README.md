# the-music-tree-genre-graph

Pure Python validation and selection for the Music Tree semantic genre graph v2.
Requires Python 3.12 or newer and jsonschema; Django is not required.

```python
from the_music_tree_genre_graph import GenreGraph, GraphValidationError, load_genre_graph_schema

graph = GenreGraph(payload)
schema = load_genre_graph_schema()
```

The package owns the bundled JSON Schema, canonical-root evaluation, node merging (`GenreGraph.merged`), typed
regional membership, scoped style expressions and attribution normalization.
Canonical roots, cultural affiliations and display parents remain distinct.
Structural examples do not approve editorial roots or memberships.

See the [contract and usage documentation](https://github.com/BehindTheMusicTree/the-music-tree-genre-kit/blob/develop/docs/genre-graph-v2.md).
Django persistence and transactions belong to `the-music-tree-genre-kit`.

This package is developed in that repository's uv workspace. A workspace source
does not propagate to Git consumers. Until the first separately authorized
publication, downstream installation requires an explicit local wheel or source;
a successful workspace install alone does not establish public availability.

See the [publication procedure](https://github.com/BehindTheMusicTree/the-music-tree-genre-kit/blob/develop/docs/genre-graph-publication.md)
for the independent tag policy, Trusted Publisher setup and release ordering.
