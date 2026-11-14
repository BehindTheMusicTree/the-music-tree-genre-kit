"""Boundary producer tests: inputs intentionally contain no computed flags."""

import pytest

from the_music_tree_genre_kit.genre_graph import GraphValidationError, boundary_witness, evaluate_boundaries


def marker(node, kind):
    return {
        "nodeId": node,
        "type": kind,
        "provenance": {"decisionId": f"{node}-{kind}", "source": "fixture", "rationale": "Synthetic decision"},
    }


def test_b04_b06_entry_below_root_and_exit_without_supplied_states():
    parents = {
        "european-art": [],
        "classical": ["european-art"],
        "breton-classical": ["classical"],
        "descendant": ["breton-classical"],
    }
    results = evaluate_boundaries(parents, [marker("classical", "entry"), marker("breton-classical", "exit")])
    assert [results[node].state for node in parents] == ["before_entry", "canonical", "after_exit", "after_exit"]
    assert boundary_witness(results, "descendant") == tuple(parents)


def test_b08_recompute_after_boundary_and_classification_edits():
    parents = {"root": [], "entry": ["root"], "exit": ["entry"], "child": ["exit"], "unrelated": []}
    markers = [marker("entry", "entry"), marker("exit", "exit")]
    original = evaluate_boundaries(parents, markers)
    removed_exit = evaluate_boundaries(parents, markers[:1])
    assert removed_exit["child"].state == "canonical"
    assert removed_exit["child"].boundary_id == "entry-entry"
    assert removed_exit["unrelated"] == original["unrelated"]
    with pytest.raises(GraphValidationError, match="from before_entry"):
        evaluate_boundaries(parents, markers[1:])
    parents["exit"] = ["root"]
    with pytest.raises(GraphValidationError, match="from before_entry"):
        evaluate_boundaries(parents, markers)
    assert original["child"].state == "after_exit"


def test_b11_e10_large_shared_ancestry_keeps_one_predecessor_per_node():
    parents = {"root": []}
    previous = ["root"]
    for level in range(1500):
        current = [f"{level}-a", f"{level}-b"]
        parents.update({node: iter(previous) for node in current})
        previous = current
    results = evaluate_boundaries(parents, [marker("root", "entry")])
    assert len(results) == 3001
    assert all(result.state == "canonical" for result in results.values())
    assert len(boundary_witness(results, previous[0])) == 1501


def test_b12_before_after_conflict_rejected_even_with_entry_at_merge():
    parents = {"root": [], "entered": ["root"], "exited": ["entered"], "merge": ["exited", "root"]}
    with pytest.raises(GraphValidationError, match="Conflicting classification") as caught:
        evaluate_boundaries(parents, [marker("entered", "entry"), marker("exited", "exit"), marker("merge", "entry")])
    assert len(caught.value.paths) == 2
    assert all(path[-1] == "merge" for path in caught.value.paths)
    assert "exited-exit" in caught.value.decisions


def test_b13_unknown_parent_and_missing_configuration_fail():
    with pytest.raises(GraphValidationError, match="Unknown classification parents"):
        evaluate_boundaries({"node": ["missing"]}, [])
    with pytest.raises(GraphValidationError, match="Missing boundary configuration"):
        evaluate_boundaries({"node": []}, None)


def test_b14_independent_entries_in_a_forest_are_valid():
    results = evaluate_boundaries({"a": [], "b": []}, [marker("a", "entry"), marker("b", "entry")])
    assert {result.state for result in results.values()} == {"canonical"}


@pytest.mark.parametrize(
    "boundary", [{}, {"nodeId": "a", "type": "entry", "provenance": {}}, {**marker("a", "entry"), "type": "unknown"}]
)
def test_b13_malformed_boundary_fails_explicitly(boundary):
    with pytest.raises(GraphValidationError, match="Invalid boundary"):
        evaluate_boundaries({"a": []}, [boundary])
