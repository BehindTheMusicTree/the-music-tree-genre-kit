#!/usr/bin/env bash
# Exercise built artifacts in a temporary consumer, outside the uv workspace.
set -euo pipefail

graph_python="${1:?Usage: check-graph-distributions.sh PYTHON_VERSION}"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
consumer_dir="$(mktemp -d)"
trap 'rm -rf "$consumer_dir"' EXIT

cp "$repo_root"/tests/test_genre_{graph,boundaries,graph_observations}.py "$consumer_dir/"
mkdir -p "$consumer_dir/fixtures"
cp -R "$repo_root/tests/fixtures/genre_graph" "$consumer_dir/fixtures/"
cd "$consumer_dir"
printf "[pytest]\n" > pytest.ini
for graph_artifact in "$repo_root"/dist/genre-graph/the_music_tree_genre_graph-*.{whl,tar.gz}; do
  uv venv --python "$graph_python" .venv
  uv pip install --python .venv/bin/python "$graph_artifact" pytest==8.1.1
  .venv/bin/python -I -c '
import importlib.util
import sys
from pathlib import Path
import the_music_tree_genre_graph as graph

if importlib.util.find_spec("django") is not None:
    raise RuntimeError("Pure distribution unexpectedly requires Django")
if not Path(graph.__file__).is_relative_to(sys.prefix):
    raise RuntimeError("Graph was imported outside the isolated environment")
graph.load_genre_graph_schema()
'
  .venv/bin/python -I -m pytest --rootdir=. -c pytest.ini -p no:cacheprovider \
    test_genre_graph.py test_genre_boundaries.py test_genre_graph_observations.py
  rm -rf .venv
done

if [[ "$graph_python" == "3.14" ]]; then
  # The wheel supplies the unpublished dependency explicitly; no workspace source is inherited.
  cp -R "$repo_root/tests" ./tests
  for kit_artifact in "$repo_root"/dist/kit/the_music_tree_genre_kit-*.{whl,tar.gz}; do
    uv venv --python "$graph_python" .venv
    uv pip install --python .venv/bin/python "$kit_artifact" \
      "$repo_root"/dist/genre-graph/the_music_tree_genre_graph-*.whl \
      pytest==8.1.1 pytest-django==4.8.0
    .venv/bin/python -m pytest --rootdir=. -c pytest.ini -p no:cacheprovider \
      --ds=tests.settings tests/test_genre_graph_storage.py
    rm -rf .venv
  done
fi
