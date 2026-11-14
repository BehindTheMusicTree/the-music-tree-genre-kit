"""Versioned graph contract; case IDs refer to the regional multiparent plan."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from the_music_tree_genre_kit.genre_graph import GenreGraph, GraphValidationError


@pytest.fixture
def payload():
    return json.loads((Path(__file__).parent / "fixtures/genre_graph/regional-v2.json").read_text())


def ref(key):
    return f"LOCAL:{key}"


def provenance(key):
    return {"decisionId": key, "source": "fixture", "rationale": "Synthetic test decision"}


def relation(child, parent, kind="classification"):
    return {"childId": ref(child), "parentId": ref(parent), "type": kind, "provenance": provenance(f"{child}-{parent}")}


def boundary(node, kind):
    return {"nodeId": ref(node), "type": kind, "provenance": provenance(f"{node}-{kind}")}


def node(payload, key):
    return next(item for item in payload["nodes"] if item["id"] == ref(key))


def test_b01_b02_b03_b06_b14_states_and_bounded_provenance(payload):
    graph = GenreGraph(payload)
    assert {key: result.state for key, result in graph.boundary_results.items()} == {
        ref("music"): "before_entry",
        ref("reggae"): "canonical",
        ref("roots"): "canonical",
        ref("dub"): "canonical",
        ref("french-reggae"): "after_exit",
        ref("french-reggae-child"): "after_exit",
        ref("breton-rock"): "before_entry",
    }
    assert graph.boundary_witness(ref("french-reggae-child")) == tuple(
        map(ref, ["music", "reggae", "french-reggae", "french-reggae-child"])
    )
    assert graph.boundary_results[ref("roots")].boundary_id == "reggae-entry"
    assert graph.boundary_results[ref("french-reggae-child")].boundary_id == "french-reggae-exit"
    assert graph.boundary_results[ref("reggae")].inherited_state == "before_entry"


@pytest.mark.parametrize(
    ("key", "kind", "message"),
    [
        ("music", "exit", "from before_entry"),
        ("roots", "entry", "from canonical"),
        ("french-reggae-child", "exit", "from after_exit"),
        ("french-reggae-child", "entry", "from after_exit"),
    ],
)
def test_b05_b07_illegal_transitions_report_decisions(payload, key, kind, message):
    payload["boundaries"].append(boundary(key, kind))
    with pytest.raises(GraphValidationError, match=message) as caught:
        GenreGraph(payload)
    assert caught.value.paths[0][-1] == ref(key)
    assert caught.value.decisions[-1] == f"{key}-{kind}"


def test_b07_both_boundaries_rejected(payload):
    payload["boundaries"].append(boundary("reggae", "exit"))
    with pytest.raises(GraphValidationError, match="Multiple boundary") as caught:
        GenreGraph(payload)
    assert set(caught.value.decisions) == {"reggae-entry", "reggae-exit"}


def test_b09_e05_order_labels_and_display_do_not_choose_state(payload):
    before = GenreGraph(payload)
    payload["nodes"].reverse()
    payload["relations"].reverse()
    payload["boundaries"].reverse()
    node(payload, "dub")["name"] = "Rewritten label"
    node(payload, "dub")["displayParentId"] = ref("reggae")
    after = GenreGraph(payload)
    assert after.boundary_results == before.boundary_results
    assert after.selected_nodes(ref("dub")) == before.selected_nodes(ref("dub"))


def test_b10_anchors_never_transmit_classification_or_songs(payload):
    before = GenreGraph(payload)
    payload["relations"] = [edge for edge in payload["relations"] if edge["type"] != "anchoring"]
    after = GenreGraph(payload)
    assert before.boundary_results == after.boundary_results
    assert before.selected_nodes(ref("jamaica")) == after.selected_nodes(ref("jamaica"))


def test_b11_compatible_classification_diamond(payload):
    payload["relations"].append(relation("dub", "roots"))
    assert GenreGraph(payload).boundary_results[ref("dub")].state == "canonical"


@pytest.mark.parametrize("parent", ["music", "french-reggae"])
def test_b12_conflicting_parents_rejected_before_local_boundary(payload, parent):
    payload["relations"].append(relation("dub", parent))
    payload["boundaries"].append(boundary("dub", "exit"))
    with pytest.raises(GraphValidationError, match="Conflicting classification") as caught:
        GenreGraph(payload)
    assert len(caught.value.paths) == 2
    assert all(path[-1] == ref("dub") for path in caught.value.paths)


@pytest.mark.parametrize("missing", ["contractVersion", "boundaries", "relations"])
def test_b13_e02_missing_configuration_is_not_an_empty_graph(payload, missing):
    del payload[missing]
    with pytest.raises(GraphValidationError, match="Invalid graph contract"):
        GenreGraph(payload)


def test_b13_unknown_boundary_and_classification_cycle(payload):
    invalid = deepcopy(payload)
    invalid["boundaries"].append(boundary("unknown", "entry"))
    with pytest.raises(GraphValidationError, match="Unknown classification boundary"):
        GenreGraph(invalid)
    payload["relations"].append(relation("music", "dub"))
    with pytest.raises(GraphValidationError, match="Cycle in classification") as caught:
        GenreGraph(payload)
    assert caught.value.paths[0][0] == caught.value.paths[0][-1]


def test_b14_explicit_empty_boundaries_is_valid():
    graph = GenreGraph(
        {
            "contractVersion": 2,
            "curationExportedOn": "2026-11-14T00:00:00Z",
            "boundaries": [],
            "relations": [],
            "nodes": [
                {"id": "LOCAL:unentered", "name": "Unentered", "kind": "genre", "canonicalState": "before_entry"}
            ],
        }
    )
    assert graph.boundary_results["LOCAL:unentered"].state == "before_entry"


def test_m01_m02_m03_m04_m16_exact_scoped_song_sets(payload):
    graph = GenreGraph(payload)
    assignments = {
        "jamaican-dub-song": {ref("jamaican-dub")},
        "french-dub-song": {ref("french-dub")},
        "british-dub-song": {ref("british-dub")},
        "unlocalized-dub-song": {ref("dub")},
        "jamaican-roots-song": {ref("jamaican-roots")},
        "french-roots-song": {ref("french-roots")},
        "genreless-song": set(),
    }

    def songs(key, scope="all"):
        selected = graph.selected_nodes(ref(key), scope=scope)
        return {song for song, genres in assignments.items() if genres & selected}

    assert songs("dub", "canonical") == {
        "jamaican-dub-song",
        "french-dub-song",
        "british-dub-song",
        "unlocalized-dub-song",
    }
    assert songs("jamaica") == {"jamaican-dub-song", "jamaican-roots-song"}
    assert songs("france") == {"french-dub-song", "french-roots-song"}
    assert songs("britain") == {"british-dub-song"}
    assert songs("roots", "canonical") == {"jamaican-roots-song", "french-roots-song"}
    assert ref("dub") not in graph.selected_nodes(ref("jamaica"))


def test_r01_r02_r03_r20_umbrella_uses_all_accepted_children(payload):
    graph = GenreGraph(payload)
    assert graph.node(ref("ancient-rome"))["isUmbrella"] is False
    assert graph.node(ref("brittany"))["isUmbrella"] is True
    assert graph.refinement_nodes([ref("ancient-rome")]) == frozenset()
    assert graph.refinement_nodes([ref("brittany")]) == {ref("brittany")}
    payload["relations"].append(relation("breton-rock", "ancient-rome", "regional_membership"))
    with pytest.raises(GraphValidationError, match="Contradictory isUmbrella"):
        GenreGraph(payload)
    node(payload, "ancient-rome")["isUmbrella"] = True
    assert GenreGraph(payload).children(ref("ancient-rome"), "regional_membership") == {ref("breton-rock")}


def test_r06_r07_r15_normalize_before_refinement_without_anchor_shortcut(payload):
    graph = GenreGraph(payload)
    assignments = list(map(ref, ["breton-rock", "brittany", "france", "jamaica"]))
    assert graph.normalize_attributions(assignments) == {ref("breton-rock"), ref("jamaica")}
    assert graph.refinement_nodes(assignments) == {ref("jamaica")}
    assert graph.normalize_attributions(map(ref, ["dub", "jamaica"])) == {ref("dub"), ref("jamaica")}
    assert graph.normalize_attributions(map(ref, ["dub", "french-dub"])) == {ref("french-dub")}


def test_r08_history_membership_is_directional(payload):
    graph = GenreGraph(payload)
    assert ref("kingdom-france") in graph.selected_nodes(ref("france"))
    assert graph.selected_nodes(ref("kingdom-france")) == {ref("kingdom-france")}


def test_r13_r14_r15_diamond_and_reduction_preserve_exact_reachability(payload):
    payload["relations"].append(relation("breton-rock", "britain", "regional_membership"))
    graph = GenreGraph(payload)
    reduced = graph.reduced_regional_relations()
    assert (ref("breton-rock"), ref("france")) not in reduced
    assert (ref("breton-rock"), ref("brittany")) in reduced
    assert (ref("breton-rock"), ref("britain")) in reduced
    payload["relations"] = [
        edge
        for edge in payload["relations"]
        if edge["type"] != "regional_membership" or (edge["childId"], edge["parentId"]) in reduced
    ]
    after = GenreGraph(payload)
    for key in graph.node_ids:
        assert after.ancestors(key, "regional_membership") == graph.ancestors(key, "regional_membership")
    subgraph = graph.ancestry_subgraph(ref("breton-rock"))
    assert len({item["id"] for item in subgraph["nodes"]}) == len(subgraph["nodes"])
    assert sum(item["id"] == ref("world") for item in subgraph["nodes"]) == 1


def test_r16_cycle_through_additional_parent_is_rejected(payload):
    payload["relations"].append(relation("france", "breton-rock", "regional_membership"))
    # Membership parents must be overviews: use a cycle consisting only of valid parent kinds.
    payload["relations"][-1] = relation("france", "brittany", "regional_membership")
    with pytest.raises(GraphValidationError, match="Cycle in regional membership") as caught:
        GenreGraph(payload)
    assert caught.value.paths[0][0] == caught.value.paths[0][-1]


@pytest.mark.parametrize(
    ("child", "parent", "kind", "message"),
    [
        ("dub", "jamaica", "regional_membership", "Canonical population"),
        ("france", "dub", "expression_style", "Invalid expression_style scope"),
        ("dub", "unknown", "classification", "Missing classification reference"),
        ("french-dub", "french-reggae", "expression_style", "style must be canonical"),
    ],
)
def test_e02_invalid_scopes_and_references(payload, child, parent, kind, message):
    payload["relations"].append(relation(child, parent, kind))
    with pytest.raises(GraphValidationError, match=message):
        GenreGraph(payload)


def test_e03_graph_roundtrip_and_snapshot_isolation(payload):
    graph = GenreGraph(payload)
    assert GenreGraph(graph.to_payload()).to_payload() == payload
    payload["nodes"].clear()
    copy = graph.to_payload()
    copy["relations"].clear()
    returned = graph.node(ref("dub"))
    returned["name"] = "mutated"
    assert graph.node(ref("dub"))["name"] == "Dub"
    assert graph.children(ref("dub"), "expression_style") == set(
        map(ref, ["jamaican-dub", "french-dub", "british-dub"])
    )


def test_e07_existing_scope_names_and_direct_coverage(payload):
    graph = GenreGraph(payload)
    canonical = graph.selected_nodes(ref("reggae"), scope="canonical")
    regional = graph.selected_nodes(ref("reggae"), scope="regional")
    assert graph.selected_nodes(ref("reggae"), scope="all") == canonical | regional
    assert ref("french-reggae") in regional - canonical
    assert ref("french-dub") in canonical & regional
    assert graph.selected_nodes(ref("dub"), include_descendants=False) == {ref("dub")}
    with pytest.raises(GraphValidationError, match="Invalid selection scope"):
        graph.selected_nodes(ref("france"), scope="canonical")


def test_m01_e07_expression_descendants_share_only_the_scoped_population(payload):
    payload["nodes"].append({"id": ref("local-dub-child"), "name": "Dub child", "kind": "expression"})
    payload["relations"].extend(
        [
            relation("local-dub-child", "french-dub", "regional_membership"),
            relation("local-dub-child", "dub", "expression_style"),
        ]
    )
    graph = GenreGraph(payload)
    for parent in ("french-dub", "france", "world"):
        assert ref("local-dub-child") in graph.selected_nodes(ref(parent))
    for scope in ("canonical", "regional", "all"):
        assert ref("local-dub-child") in graph.selected_nodes(ref("dub"), scope=scope)
    assert ref("local-dub-child") not in graph.selected_nodes(ref("jamaica"))
    assert graph.normalize_attributions(map(ref, ["local-dub-child", "french-dub", "france", "dub"])) == {
        ref("local-dub-child")
    }


def test_b01_m03_e07_before_entry_prefix_does_not_transmit_a_canonical_interval(payload):
    payload["relations"].append(relation("music", "france", "regional_membership"))
    graph = GenreGraph(payload)
    assert graph.selected_nodes(ref("music")) == {ref("music")}
    assert ref("dub") not in graph.selected_nodes(ref("france"))
    assert ref("jamaican-dub") not in graph.selected_nodes(ref("france"))
    assert graph.normalize_attributions(map(ref, ["music", "dub"])) == set(map(ref, ["music", "dub"]))


def test_r03_r06_noncanonical_classification_descendants_transmit_to_regional_parents(payload):
    payload["relations"] = [
        edge
        for edge in payload["relations"]
        if not (edge["childId"] == ref("french-reggae-child") and edge["type"] == "regional_membership")
    ]
    graph = GenreGraph(payload)
    assert graph.selected_nodes(ref("french-reggae")) == set(map(ref, ["french-reggae", "french-reggae-child"]))
    assert ref("french-reggae-child") in graph.selected_nodes(ref("france"))
    ancestry = graph.ancestry_subgraph(ref("french-reggae-child"))
    assert {item["id"] for item in ancestry["nodes"]} == set(
        map(ref, ["french-reggae-child", "french-reggae", "france", "world"])
    )
    assert (ref("french-reggae-child"), ref("french-reggae"), "classification") in {
        (edge["childId"], edge["parentId"], edge["type"]) for edge in ancestry["relations"]
    }
    assert graph.normalize_attributions(map(ref, ["french-reggae-child", "french-reggae", "france", "reggae"])) == {
        ref("french-reggae-child")
    }


def test_r16_combined_population_cycle_is_invalid(payload):
    payload["relations"].append(relation("french-reggae", "french-reggae-child", "regional_membership"))
    with pytest.raises(GraphValidationError, match="Cycle in population") as caught:
        GenreGraph(payload)
    assert caught.value.paths[0][0] == caught.value.paths[0][-1]


def test_e07_normalization_preserves_every_inclusive_selection(payload):
    graph = GenreGraph(payload)
    direct = graph.node_ids
    normalized = graph.normalize_attributions(direct)
    for selected in graph.node_ids:
        population = graph.selected_nodes(selected)
        assert bool(direct & population) == bool(normalized & population)


def test_r17_goryeo_child_with_another_display_parent_is_not_a_leaf(payload):
    for key, label, umbrella in (
        ("goryeo", "Goryeo", True),
        ("later-silla", "Later Silla", False),
        ("korea", "Korea", True),
    ):
        payload["nodes"].append(
            {
                "id": ref(key),
                "name": label,
                "kind": "overview",
                "overviewType": "historical",
                "overviewProvenance": provenance(key),
                "isUmbrella": umbrella,
            }
        )
    node(payload, "later-silla")["displayParentId"] = ref("korea")
    payload["relations"].extend(
        [
            relation("later-silla", "goryeo", "regional_membership"),
            relation("later-silla", "korea", "regional_membership"),
        ]
    )
    graph = GenreGraph(payload)
    assert graph.children(ref("goryeo"), "regional_membership") == {ref("later-silla")}
    assert graph.selected_nodes(ref("goryeo")) == set(map(ref, ["goryeo", "later-silla"]))
    assert graph.refinement_nodes([ref("goryeo")]) == {ref("goryeo")}
    assert graph.refinement_nodes([ref("later-silla")]) == set()


@pytest.mark.parametrize("key", ["sasanian-empire", "gascony", "bosnia-herzegovina-socialist", "later-silla"])
def test_r18_named_structural_witnesses_reuse_one_identity_with_parallel_parents(payload, key):
    payload["nodes"].append(
        {
            "id": ref(key),
            "name": key,
            "kind": "overview",
            "overviewType": "historical",
            "overviewProvenance": provenance(key),
            "isUmbrella": False,
            "displayParentId": ref("france"),
        }
    )
    # These deliberately synthetic parents exercise graph shape, not historical geography.
    payload["relations"].extend(
        [
            relation(key, "france", "regional_membership"),
            relation(key, "britain", "regional_membership"),
        ]
    )
    graph = GenreGraph(payload)
    assert sum(item["id"] == ref(key) for item in graph.to_payload()["nodes"]) == 1
    assert ref(key) in graph.selected_nodes(ref("france")) & graph.selected_nodes(ref("britain"))
    assert graph.parents(ref(key), "regional_membership") == set(map(ref, ["france", "britain"]))


def test_e03_legacy_metadata_survives_semantic_roundtrip(payload):
    metadata = {
        "side": "pop",
        "isUnacceptedRoot": True,
        "scene": "commercial",
        "summary": "Summary",
        "description": "Description",
        "summarySourceUrl": "https://example.org/source",
        "image": {
            "url": "https://example.org/image",
            "pageUrl": "https://example.org/page",
            "author": None,
            "license": "CC0",
            "licenseUrl": None,
        },
    }
    node(payload, "dub").update(metadata)
    graph = GenreGraph(payload)
    assert GenreGraph(graph.to_payload()).to_payload() == payload
    assert all(graph.node(ref("dub"))[key] == value for key, value in metadata.items())


@pytest.mark.parametrize(
    ("field", "value"),
    [("side", "core"), ("scene", "unknown"), ("image", {}), ("summary", ""), ("isUnacceptedRoot", False)],
)
def test_e02_invalid_legacy_metadata_rejected(payload, field, value):
    node(payload, "dub")[field] = value
    with pytest.raises(GraphValidationError, match="Invalid graph contract"):
        GenreGraph(payload)


def test_e02_identity_limit_matches_sql_storage(payload):
    node(payload, "dub")["id"] = "LOCAL:" + "x" * 250
    with pytest.raises(GraphValidationError, match="too long"):
        GenreGraph(payload)
