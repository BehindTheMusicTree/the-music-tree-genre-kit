"""The Gold genre-tree JSON Schema, owned here because this package defines the import contract it describes."""

import json
from importlib.resources import files
from importlib.resources.abc import Traversable

GENRE_TREE_SCHEMA_PATH: Traversable = files("the_music_tree_genre_kit") / "schemas" / "genre_tree.schema.json"


def load_genre_tree_schema() -> dict:
    return json.loads(GENRE_TREE_SCHEMA_PATH.read_text(encoding="utf-8"))
