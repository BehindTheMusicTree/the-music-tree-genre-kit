"""Replay observed graph structure; these fixtures do not approve musical inclusion."""

import hashlib
import json
from pathlib import Path

import pytest

from the_music_tree_genre_kit.genre_graph import GenreGraph, GraphValidationError

OBSERVATIONS = Path(__file__).parent / "fixtures/genre_graph/observed-additional-children.json"
CASES = json.loads(OBSERVATIONS.read_text())


def provenance():
    return {
        "decisionId": "structural-replay",
        "source": "diagnostic:2026-11-13",
        "rationale": "Test role only; not approved musical inclusion or overview chronology",
    }


def overview(identity, name, umbrella):
    return {
        "id": identity,
        "name": name,
        "kind": "overview",
        "overviewType": "historical",
        "overviewProvenance": provenance(),
        "isUmbrella": umbrella,
    }


def test_r19_observation_inventory_is_complete_and_frozen():
    assert len(CASES) == len({case["overview_id"] for case in CASES}) == 44
    assert hashlib.sha256(OBSERVATIONS.read_bytes()).hexdigest() == (
        "a3496975abd53eb0fa4752c6288b860f23a22d932976e574934f39a25b8b339b"
    )
    assert all(case["additional_children"] for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=[case["overview_id"] for case in CASES])
def test_r19_all_observed_additional_children_drive_umbrella_validation(case):
    parent = case["overview_id"]
    other = "LOCAL:other-display-parent"
    nodes = [overview(parent, case["overview_label"], True), overview(other, "Other display parent", True)]
    edges = []
    for child in case["additional_children"]:
        nodes.append(
            {
                "id": child["id"],
                "name": child["label"],
                "kind": "genre",
                "canonicalState": "before_entry",
                "displayParentId": other,
            }
        )
        edges.extend(
            {"childId": child["id"], "parentId": destination, "type": "regional_membership", "provenance": provenance()}
            for destination in (parent, other)
        )
    payload = {
        "contractVersion": 2,
        "curationExportedOn": "2026-11-14T00:00:00Z",
        "nodes": nodes,
        "relations": edges,
        "boundaries": [],
    }
    graph = GenreGraph(payload)
    expected = {child["id"] for child in case["additional_children"]}
    assert graph.children(parent, "regional_membership") == expected
    assert graph.selected_nodes(parent) == expected | {parent}
    assert graph.refinement_nodes([parent]) == {parent}
    nodes[0]["isUmbrella"] = False
    with pytest.raises(GraphValidationError, match="Contradictory isUmbrella"):
        GenreGraph(payload)


@pytest.mark.parametrize("child_kind", ["predecessor", "territory", "genre", "expression"])
@pytest.mark.parametrize("additional", [False, True])
def test_r03_all_four_child_roles_and_display_positions(child_kind, additional):
    parent, other, child, style = "LOCAL:parent", "LOCAL:other", "LOCAL:child", "LOCAL:style"
    nodes = [overview(parent, "Parent", True)]
    child_node = {"id": child, "name": "Child", "displayParentId": other if additional else parent}
    if child_kind in {"predecessor", "territory"}:
        child_node.update(overview(child, "Child", False))
    elif child_kind == "genre":
        child_node.update(kind="genre", canonicalState="before_entry")
    else:
        child_node.update(kind="expression")
    nodes.append(child_node)
    edges = [{"childId": child, "parentId": parent, "type": "regional_membership", "provenance": provenance()}]
    boundaries = []
    if additional:
        nodes.append(overview(other, "Other parent", True))
        edges.append({**edges[0], "parentId": other})
    if child_kind == "expression":
        nodes.append({"id": style, "name": "Style", "kind": "genre", "canonicalState": "canonical"})
        boundaries.append({"nodeId": style, "type": "entry", "provenance": provenance()})
        edges.append({"childId": child, "parentId": style, "type": "expression_style", "provenance": provenance()})
    graph = GenreGraph(
        {
            "contractVersion": 2,
            "curationExportedOn": "2026-11-14T00:00:00Z",
            "nodes": nodes,
            "relations": edges,
            "boundaries": boundaries,
        }
    )
    assert graph.children(parent, "regional_membership") == {child}
    assert graph.node(parent)["isUmbrella"] is True
