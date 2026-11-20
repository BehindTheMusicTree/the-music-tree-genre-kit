"""Versioned graph contract; case IDs refer to the regional multiparent plan."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from the_music_tree_genre_graph import GenreGraph, GraphValidationError


@pytest.fixture
def payload():
    return json.loads((Path(__file__).parent / "fixtures/genre_graph/regional-v2.json").read_text())


def ref(key):
    return f"LOCAL:{key}"


def provenance(key):
    return {"decisionId": key, "source": "fixture", "rationale": "Synthetic test decision"}


def relation(child, parent, kind="classification"):
    return {"childId": ref(child), "parentId": ref(parent), "type": kind, "provenance": provenance(f"{child}-{parent}")}


def node(payload, key):
    return next(item for item in payload["nodes"] if item["id"] == ref(key))


def genre(key):
    return {"id": ref(key), "name": key, "kind": "genre"}


def overview(key, umbrella=True, overview_type="current"):
    return {
        "id": ref(key),
        "name": key,
        "kind": "overview",
        "overviewType": overview_type,
        "overviewProvenance": provenance(key),
        "isUmbrella": umbrella,
    }


def test_c02_canonical_state_propagates_from_listed_roots(payload):
    graph = GenreGraph(payload)
    assert {
        key: graph.canonical_state(ref(key)) for key in ["reggae", "roots", "dub", "reggae-fusion"]
    } == dict.fromkeys(["reggae", "roots", "dub", "reggae-fusion"], "canonical")
    for key in ["breton-rock", "country", "bluegrass", "french-reggae-child"]:
        assert graph.canonical_state(ref(key)) == "regional"
    for key in ["french-dub", "jamaica"]:
        assert graph.canonical_state(ref(key)) is None


def test_c01_unlisted_root_without_region_is_rejected(payload):
    payload["nodes"].append(genre("orphan"))
    with pytest.raises(GraphValidationError, match="Regional node reaches no overview"):
        GenreGraph(payload)


def test_c01_listing_the_root_makes_it_canonical(payload):
    payload["nodes"].append(genre("orphan"))
    payload["canonicalRoots"].append({"nodeId": ref("orphan"), "provenance": provenance("orphan-root")})
    assert GenreGraph(payload).canonical_state(ref("orphan")) == "canonical"


def test_c03_mixed_classification_edge_is_rejected(payload):
    payload["nodes"].append(genre("hybrid"))
    payload["relations"].extend([relation("hybrid", "reggae"), relation("hybrid", "country")])
    with pytest.raises(GraphValidationError, match="mixes canonical and regional parents") as caught:
        GenreGraph(payload)
    assert set(caught.value.paths) == {(ref("reggae"), ref("hybrid")), (ref("country"), ref("hybrid"))}


@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("unknown", "Unknown canonical root"),
        ("reggae", "Duplicate canonical root"),
        ("french-dub", "not a genre"),
        ("roots", "has a classification parent"),
    ],
)
def test_c04_invalid_canonical_roots_rejected(payload, key, message):
    payload["canonicalRoots"].append({"nodeId": ref(key), "provenance": provenance(f"{key}-root")})
    with pytest.raises(GraphValidationError, match=message):
        GenreGraph(payload)


def test_c05_explicit_empty_roots_is_valid():
    graph = GenreGraph(
        {
            "contractVersion": 2,
            "curationExportedOn": "2026-11-14T00:00:00Z",
            "canonicalRoots": [],
            "relations": [],
            "nodes": [overview("lonely")],
        }
    )
    assert graph.canonical_state(ref("lonely")) is None


def test_b09_e05_order_labels_and_display_do_not_choose_state(payload):
    before = GenreGraph(payload)
    payload["nodes"].reverse()
    payload["relations"].reverse()
    node(payload, "dub")["name"] = "Rewritten label"
    node(payload, "dub")["displayParentId"] = ref("reggae")
    after = GenreGraph(payload)
    assert {key: after.canonical_state(key) for key in after.node_ids} == {
        key: before.canonical_state(key) for key in before.node_ids
    }
    assert after.selected_nodes(ref("dub")) == before.selected_nodes(ref("dub"))


def test_b10_anchors_never_transmit_classification_or_songs(payload):
    before = GenreGraph(payload)
    payload["relations"] = [edge for edge in payload["relations"] if edge["type"] != "anchoring"]
    after = GenreGraph(payload)
    assert before.selected_nodes(ref("jamaica")) == after.selected_nodes(ref("jamaica"))


def test_b11_compatible_classification_diamond(payload):
    payload["relations"].append(relation("dub", "roots"))
    assert GenreGraph(payload).canonical_state(ref("dub")) == "canonical"


@pytest.mark.parametrize("missing", ["contractVersion", "canonicalRoots", "relations"])
def test_b13_e02_missing_configuration_is_not_an_empty_graph(payload, missing):
    del payload[missing]
    with pytest.raises(GraphValidationError, match="Invalid graph contract"):
        GenreGraph(payload)


@pytest.mark.parametrize("legacy", ["boundaries", "canonicalState", "isUnacceptedRoot"])
def test_removed_boundary_fields_are_rejected(payload, legacy):
    if legacy == "boundaries":
        payload[legacy] = []
    else:
        node(payload, "dub")[legacy] = "canonical" if legacy == "canonicalState" else True
    with pytest.raises(GraphValidationError, match="Invalid graph contract"):
        GenreGraph(payload)


def test_b13_classification_cycle(payload):
    payload["relations"].append(relation("reggae", "dub"))
    with pytest.raises(GraphValidationError, match="Cycle in classification") as caught:
        GenreGraph(payload)
    assert caught.value.paths[0][0] == caught.value.paths[0][-1]


def test_x01_country_and_usa_selections(payload):
    graph = GenreGraph(payload)
    assert graph.selected_nodes(ref("usa")) == set(map(ref, ["usa", "country", "bluegrass"]))
    assert graph.selected_nodes(ref("country")) == set(
        map(ref, ["country", "bluegrass", "french-country", "french-bluegrass"])
    )
    assert graph.selected_nodes(ref("france")) >= set(map(ref, ["french-country", "french-bluegrass"]))
    assert {ref("french-country"), ref("french-bluegrass")}.isdisjoint(graph.selected_nodes(ref("usa")))


def test_x02_normalization_keeps_usa_and_french_country(payload):
    graph = GenreGraph(payload)
    assert graph.normalize_attributions(map(ref, ["usa", "french-country"])) == set(map(ref, ["usa", "french-country"]))
    assert graph.normalize_attributions(map(ref, ["usa", "country", "bluegrass"])) == {ref("bluegrass")}
    assert graph.ancestors(ref("french-bluegrass"), "population") == set(map(ref, ["france", "world"]))


def test_x03_expression_inside_the_region_of_its_regional_style_is_rejected(payload):
    payload["nodes"].extend([overview("texas"), genre("x") | {"kind": "expression"}])
    payload["nodes"][-1]["id"] = ref("texas-country")
    payload["relations"].extend(
        [
            relation("texas", "usa", "regional_membership"),
            relation("texas-country", "country", "expression_style"),
            relation("texas-country", "texas", "regional_membership"),
        ]
    )
    with pytest.raises(GraphValidationError, match="shares every region with its regional style"):
        GenreGraph(payload)


def test_x04_regional_expression_without_overview_is_rejected(payload):
    payload["nodes"].append({"id": ref("floating-country"), "name": "x", "kind": "expression"})
    payload["relations"].append(relation("floating-country", "country", "expression_style"))
    with pytest.raises(GraphValidationError, match="Regional node reaches no overview"):
        GenreGraph(payload)


def test_scopes_split_the_node_from_its_regional_expressions(payload):
    graph = GenreGraph(payload)
    canonical = graph.selected_nodes(ref("reggae"), scope="canonical")
    regional = graph.selected_nodes(ref("reggae"), scope="regional")
    assert canonical == set(map(ref, ["reggae", "roots", "dub", "reggae-fusion"]))
    assert canonical & regional == {ref("reggae")}
    assert graph.selected_nodes(ref("reggae"), scope="all") == canonical | regional
    assert ref("french-dub") in regional and ref("french-reggae-child") in regional
    with pytest.raises(GraphValidationError, match="Invalid selection scope"):
        graph.selected_nodes(ref("country"), scope="regional")


def access_ancestors(graph, start):
    """Independent walk: climb membership/classification, jump once to a style, then climb classification only."""
    found, seen, pending = set(), set(), [(start, False)]
    while pending:
        current, jumped = pending.pop()
        if (current, jumped) in seen:
            continue
        seen.add((current, jumped))
        steps = [(parent, jumped) for parent in graph.parents(current, "classification")]
        if not jumped:
            steps += [(parent, False) for parent in graph.parents(current, "regional_membership")]
            steps += [(style, True) for style in graph.parents(current, "expression_style")]
        for parent, flag in steps:
            found.add(parent)
            pending.append((parent, flag))
    return found


def test_selection_is_the_inverse_of_typed_access(payload):
    graph = GenreGraph(payload)
    for member in graph.node_ids:
        for ancestor in graph.node_ids - {member}:
            assert (ancestor in access_ancestors(graph, member)) == (
                member in graph.selected_nodes(ancestor, scope="all")
            ), (member, ancestor)


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

    assert songs("dub", "canonical") == {"unlocalized-dub-song"}
    assert songs("dub", "regional") == {"jamaican-dub-song", "french-dub-song", "british-dub-song"} | {
        "unlocalized-dub-song"
    }
    assert songs("dub") == songs("dub", "regional")
    assert songs("jamaica") == {"jamaican-dub-song", "jamaican-roots-song"}
    assert songs("france") == {"french-dub-song", "french-roots-song"}
    assert songs("britain") == {"british-dub-song"}
    assert songs("roots", "canonical") == set()
    assert songs("roots") == {"jamaican-roots-song", "french-roots-song"}
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
        ("french-dub", "french-reggae", "expression_style", "Invalid expression_style scope"),
        ("reggae-fusion", "france", "regional_membership", "cannot be a regional member"),
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


def test_e07_direct_coverage_and_scope_rules(payload):
    graph = GenreGraph(payload)
    assert ref("french-reggae-fusion") in graph.selected_nodes(ref("reggae"), scope="regional")
    assert ref("french-reggae-fusion") not in graph.selected_nodes(ref("reggae"), scope="canonical")
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
    for scope in ("regional", "all"):
        assert ref("local-dub-child") in graph.selected_nodes(ref("dub"), scope=scope)
    assert ref("local-dub-child") not in graph.selected_nodes(ref("dub"), scope="canonical")
    assert ref("local-dub-child") not in graph.selected_nodes(ref("jamaica"))
    assert graph.normalize_attributions(map(ref, ["local-dub-child", "french-dub", "france", "dub"])) == {
        ref("local-dub-child")
    }


def test_r03_r06_canonical_genre_transmits_its_expressions_to_regional_parents(payload):
    graph = GenreGraph(payload)
    assert graph.selected_nodes(ref("reggae-fusion")) == set(map(ref, ["reggae-fusion", "french-reggae-fusion"]))
    assert ref("french-reggae-fusion") in graph.selected_nodes(ref("france"))
    assert ref("french-reggae-fusion") in graph.selected_nodes(ref("reggae"), scope="all")
    assert graph.normalize_attributions(map(ref, ["french-reggae-fusion", "france", "reggae-fusion"])) == {
        ref("french-reggae-fusion")
    }


def test_style_jump_is_taken_once(payload):
    payload["nodes"].extend(
        [genre("fusion-root"), {"id": ref("fusion-root-expression"), "name": "x", "kind": "expression"}]
    )
    payload["relations"].extend(
        [
            relation("fusion-root", "french-dub", "regional_membership"),
            relation("fusion-root-expression", "fusion-root", "expression_style"),
            relation("fusion-root-expression", "britain", "regional_membership"),
        ]
    )
    graph = GenreGraph(payload)
    assert ref("fusion-root") in graph.selected_nodes(ref("dub"))
    assert ref("fusion-root-expression") not in graph.selected_nodes(ref("dub"))
    assert ref("fusion-root-expression") in graph.selected_nodes(ref("britain"))
    assert graph.normalize_attributions(map(ref, ["dub", "fusion-root-expression"])) == set(
        map(ref, ["dub", "fusion-root-expression"])
    )


def test_expression_with_regional_population_selected_via_regional_root(payload):
    graph = GenreGraph(payload)
    assert graph.selected_nodes(ref("french-reggae")) == set(map(ref, ["french-reggae", "french-reggae-child"]))
    assert ref("french-reggae-child") in graph.selected_nodes(ref("reggae"), scope="all")
    assert ref("french-reggae-child") in graph.selected_nodes(ref("reggae"), scope="regional")


def test_classified_regional_genre_is_rejected(payload):
    payload["relations"].append(relation("breton-rock", "country"))
    with pytest.raises(GraphValidationError, match="Classified genre cannot be a regional member"):
        GenreGraph(payload)


def test_r16_combined_population_cycle_is_invalid(payload):
    payload["relations"].append(relation("french-reggae", "french-reggae-child", "regional_membership"))
    with pytest.raises(GraphValidationError, match="Cycle in regional membership") as caught:
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
    [("side", "core"), ("scene", "unknown"), ("image", {}), ("summary", "")],
)
def test_e02_invalid_legacy_metadata_rejected(payload, field, value):
    node(payload, "dub")[field] = value
    with pytest.raises(GraphValidationError, match="Invalid graph contract"):
        GenreGraph(payload)


def test_e02_identity_limit_matches_sql_storage(payload):
    node(payload, "dub")["id"] = "LOCAL:" + "x" * 250
    with pytest.raises(GraphValidationError, match="too long"):
        GenreGraph(payload)


def merge_provenance():
    return provenance("merge")


def test_merged_moves_relations_and_removes_the_source(payload):
    graph = GenreGraph(payload)
    merged = graph.merged(ref("roots"), ref("dub"), merge_provenance())
    assert ref("roots") not in merged.node_ids
    assert merged.parents(ref("jamaican-roots"), "expression_style") == {ref("dub")}
    assert merged.parents(ref("dub"), "classification") == {ref("reggae")}
    assert merged.canonical_state(ref("dub")) == "canonical"
    assert graph.node_ids >= {ref("roots")}


def test_merged_is_idempotent_and_ignores_a_missing_source(payload):
    merged = GenreGraph(payload).merged(ref("roots"), ref("dub"), merge_provenance())
    assert merged.merged(ref("roots"), ref("dub"), merge_provenance()) is merged


def test_merged_root_into_its_canonical_descendant_passes_rootship_on(payload):
    merged = GenreGraph(payload).merged(ref("reggae"), ref("dub"), merge_provenance())
    assert merged.to_payload()["canonicalRoots"] == [{"nodeId": ref("dub"), "provenance": merge_provenance()}]
    assert merged.parents(ref("roots"), "classification") == {ref("dub")}
    assert merged.parents(ref("dub"), "classification") == frozenset()
    assert all(merged.canonical_state(ref(key)) == "canonical" for key in ["dub", "roots", "reggae-fusion"])


def test_merged_rejects_a_root_that_would_become_a_regional_member(payload):
    with pytest.raises(GraphValidationError, match="Canonical population cannot be a regional member"):
        GenreGraph(payload).merged(ref("reggae"), ref("country"), merge_provenance())


def test_merged_overview_recomputes_umbrella(payload):
    merged = GenreGraph(payload).merged(ref("brittany"), ref("ancient-rome"), merge_provenance())
    assert merged.node(ref("ancient-rome"))["isUmbrella"] is True
    assert merged.children(ref("ancient-rome"), "regional_membership") == {ref("breton-rock")}


def test_merged_rejects_cycles_kinds_and_unknown_target(payload):
    graph = GenreGraph(payload)
    with pytest.raises(GraphValidationError, match="Cycle in regional membership"):
        graph.merged(ref("world"), ref("brittany"), merge_provenance())
    with pytest.raises(GraphValidationError, match="different kinds"):
        graph.merged(ref("dub"), ref("jamaica"), merge_provenance())
    with pytest.raises(GraphValidationError, match="Unknown merge target"):
        graph.merged(ref("dub"), ref("nowhere"), merge_provenance())
    with pytest.raises(GraphValidationError, match="into itself"):
        graph.merged(ref("dub"), ref("dub"), merge_provenance())
