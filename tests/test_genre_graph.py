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


def test_c02_state_and_edge_kinds(payload):
    graph = GenreGraph(payload)
    for key in ["reggae", "roots", "dub", "reggae-fusion", "country", "bluegrass"]:
        assert graph.state(ref(key)) == "canonical"
    for key in ["breton-rock", "french-reggae", "french-reggae-child", "french-dub", "jamaican-roots"]:
        assert graph.state(ref(key)) == "regional"
    for key in ["jamaica", "france"]:
        assert graph.state(ref(key)) is None
    assert graph.regions(ref("french-reggae-child")) == {ref("france")}
    assert graph.regions(ref("breton-rock")) == {ref("brittany"), ref("france")}
    assert graph.edge_kind(ref("dub"), ref("reggae")) == "restricted"
    assert graph.edge_kind(ref("bluegrass"), ref("country")) == "restricted"
    assert graph.edge_kind(ref("french-country"), ref("country")) == "expression"
    assert graph.edge_kind(ref("french-reggae-child"), ref("french-reggae")) == "restricted"
    assert graph.expression_parents(ref("jamaican-dub")) == {ref("dub")}
    assert graph.expression_parents(ref("french-reggae-child")) == frozenset()


def test_c01_isolated_genre_is_rejected(payload):
    payload["nodes"].append(genre("orphan"))
    with pytest.raises(GraphValidationError, match="Genre without region or canonical root"):
        GenreGraph(payload)


def test_c01_listing_the_root_makes_it_canonical(payload):
    payload["nodes"].append(genre("orphan"))
    payload["canonicalRoots"].append({"nodeId": ref("orphan"), "provenance": provenance("orphan-root")})
    assert GenreGraph(payload).state(ref("orphan")) == "canonical"


def test_c03_non_localized_genre_under_canonical_and_regional_parents_is_regional(payload):
    payload["nodes"].append(genre("hybrid"))
    payload["relations"].extend([relation("hybrid", "reggae"), relation("hybrid", "french-reggae")])
    graph = GenreGraph(payload)
    assert graph.state(ref("hybrid")) == "regional"
    assert graph.regions(ref("hybrid")) == {ref("france")}
    assert graph.edge_kind(ref("hybrid"), ref("reggae")) == "expression"
    assert graph.edge_kind(ref("hybrid"), ref("french-reggae")) == "restricted"
    assert ref("hybrid") not in graph.selected_nodes(ref("reggae"), scope="restricted")
    assert ref("hybrid") in graph.selected_nodes(ref("reggae"), scope="expressions")


def test_c03_child_broader_than_its_parent_is_rejected(payload):
    payload["nodes"].append(genre("worldwide-reggae"))
    payload["relations"].extend(
        [relation("worldwide-reggae", "french-reggae"), relation("worldwide-reggae", "world", "regional_membership")]
    )
    with pytest.raises(GraphValidationError, match="broader than its classification parent") as caught:
        GenreGraph(payload)
    assert caught.value.paths == ((ref("worldwide-reggae"), ref("french-reggae")),)


def test_c03_partial_overlap_or_disjoint_regions_are_expressions(payload):
    payload["nodes"].append(genre("belgian-reggae"))
    payload["nodes"].append(overview("belgium"))
    payload["relations"].extend(
        [
            relation("belgium", "world", "regional_membership"),
            relation("belgian-reggae", "french-reggae"),
            relation("belgian-reggae", "belgium", "regional_membership"),
        ]
    )
    graph = GenreGraph(payload)
    assert graph.edge_kind(ref("belgian-reggae"), ref("french-reggae")) == "expression"
    assert ref("belgian-reggae") not in graph.selected_nodes(ref("france"))


def test_c03_broader_than_one_parent_but_inside_another_is_accepted(payload):
    payload["nodes"].append(genre("hybrid"))
    payload["relations"].extend(
        [relation("hybrid", "french-reggae"), relation("hybrid", "jamaica", "regional_membership")]
    )
    graph = GenreGraph(payload)
    assert graph.edge_kind(ref("hybrid"), ref("french-reggae")) == "expression"


@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("unknown", "Unknown canonical root"),
        ("reggae", "Duplicate canonical root"),
        ("france", "not a genre"),
        ("roots", "has a classification parent"),
    ],
)
def test_c04_invalid_canonical_roots_rejected(payload, key, message):
    payload["canonicalRoots"].append({"nodeId": ref(key), "provenance": provenance(f"{key}-root")})
    with pytest.raises(GraphValidationError, match=message):
        GenreGraph(payload)


def test_c04_listed_root_cannot_be_a_regional_member(payload):
    payload["nodes"].append(genre("rooted"))
    payload["relations"].append(relation("rooted", "france", "regional_membership"))
    payload["canonicalRoots"].append({"nodeId": ref("rooted"), "provenance": provenance("rooted-root")})
    with pytest.raises(GraphValidationError, match="cannot be a regional member"):
        GenreGraph(payload)


def test_c05_explicit_empty_roots_is_valid():
    graph = GenreGraph(
        {
            "contractVersion": 4,
            "curationExportedOn": "2026-11-14T00:00:00Z",
            "canonicalRoots": [],
            "relations": [],
            "nodes": [overview("lonely")],
        }
    )
    assert graph.state(ref("lonely")) is None


def test_b09_e05_order_labels_and_display_do_not_choose_state(payload):
    before = GenreGraph(payload)
    payload["nodes"].reverse()
    payload["relations"].reverse()
    node(payload, "dub")["name"] = "Rewritten label"
    node(payload, "dub")["displayParentId"] = ref("reggae")
    after = GenreGraph(payload)
    assert {key: after.state(key) for key in after.node_ids} == {key: before.state(key) for key in before.node_ids}
    assert after.selected_nodes(ref("dub")) == before.selected_nodes(ref("dub"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(contractVersion=3),
        lambda p: p["relations"].append(relation("french-dub", "dub", "expression_style")),
        lambda p: p["relations"].append(relation("dub", "jamaica", "anchoring")),
        lambda p: node(p, "dub").update(kind="expression"),
    ],
)
def test_b10_removed_contract_elements_are_rejected(payload, mutate):
    mutate(payload)
    with pytest.raises(GraphValidationError, match="Invalid graph contract"):
        GenreGraph(payload)


def test_b11_compatible_classification_diamond(payload):
    payload["relations"].append(relation("dub", "roots"))
    assert GenreGraph(payload).state(ref("dub")) == "canonical"


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
    assert graph.selected_nodes(ref("country"), scope="restricted") == set(map(ref, ["country", "bluegrass"]))
    assert graph.selected_nodes(ref("country"), scope="expressions") == set(
        map(ref, ["french-country", "french-bluegrass"])
    )
    assert graph.selected_nodes(ref("country")) == set(
        map(ref, ["country", "bluegrass", "french-country", "french-bluegrass"])
    )
    assert graph.selected_nodes(ref("france")) >= set(map(ref, ["french-country", "french-bluegrass"]))
    assert {ref("french-country"), ref("french-bluegrass")}.isdisjoint(graph.selected_nodes(ref("usa")))
    assert graph.selected_nodes(ref("usa")) == {ref("usa")}


def test_x02_normalization_keeps_usa_and_french_country(payload):
    graph = GenreGraph(payload)
    assert graph.normalize_attributions(map(ref, ["usa", "french-country"])) == set(map(ref, ["usa", "french-country"]))
    assert graph.normalize_attributions(map(ref, ["country", "bluegrass"])) == {ref("bluegrass")}
    assert graph.ancestors(ref("french-bluegrass"), "restricted") == set(map(ref, ["france", "world"]))


def test_scopes_split_the_restricted_from_the_expressions(payload):
    graph = GenreGraph(payload)
    restricted = graph.selected_nodes(ref("reggae"), scope="restricted")
    expressions = graph.selected_nodes(ref("reggae"), scope="expressions")
    assert restricted == set(map(ref, ["reggae", "roots", "dub", "reggae-fusion"]))
    assert not restricted & expressions
    assert ref("reggae") not in expressions
    assert graph.selected_nodes(ref("reggae"), scope="extended") == restricted | expressions
    assert ref("french-dub") in expressions and ref("french-reggae-child") in expressions
    assert graph.selected_nodes(ref("france"), scope="expressions") == frozenset()
    with pytest.raises(GraphValidationError, match="Invalid selection scope"):
        graph.selected_nodes(ref("country"), scope="all")


def access_ancestors(graph, start):
    """Independent walk: classification ancestors via every edge, plus the node's own regions and their ancestors."""
    found, pending = set(), [start]
    while pending:
        current = pending.pop()
        for parent in graph.parents(current, "classification"):
            if parent not in found:
                found.add(parent)
                pending.append(parent)
    regions = set(graph.regions(start)) if graph.node(start)["kind"] == "genre" else {start}
    pending = list(regions)
    while pending:
        current = pending.pop()
        for parent in graph.parents(current, "regional_membership"):
            if parent not in regions:
                regions.add(parent)
                pending.append(parent)
    return found | (regions - {start})


def test_selection_is_the_inverse_of_typed_access(payload):
    graph = GenreGraph(payload)
    for member in graph.node_ids:
        for ancestor in graph.node_ids - {member}:
            assert (ancestor in access_ancestors(graph, member)) == (
                member in graph.selected_nodes(ancestor, scope="extended")
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

    def songs(key, scope="extended"):
        selected = graph.selected_nodes(ref(key), scope=scope)
        return {song for song, genres in assignments.items() if genres & selected}

    assert songs("dub", "restricted") == {"unlocalized-dub-song"}
    assert songs("dub", "expressions") == {"jamaican-dub-song", "french-dub-song", "british-dub-song"}
    assert songs("dub") == songs("dub", "restricted") | songs("dub", "expressions")
    assert songs("jamaica") == {"jamaican-dub-song", "jamaican-roots-song"}
    assert songs("france") == {"french-dub-song", "french-roots-song"}
    assert songs("britain") == {"british-dub-song"}
    assert songs("roots", "restricted") == set()
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


def test_r06_r07_r15_normalize_before_refinement(payload):
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
        ("france", "dub", "classification", "Invalid classification scope"),
        ("france", "dub", "regional_membership", "Invalid regional_membership scope"),
        ("dub", "unknown", "classification", "Missing classification reference"),
        ("french-dub", "french-reggae", "expression_style", "Invalid graph contract"),
        ("reggae", "france", "regional_membership", "Canonical root cannot be a regional member"),
        ("dub", "reggae", "classification", "Duplicate classification relation"),
        ("dub", "french-reggae", "classification", None),
    ],
)
def test_e02_invalid_scopes_and_references(payload, child, parent, kind, message):
    payload["relations"].append(relation(child, parent, kind))
    if message is None:
        GenreGraph(payload)
        return
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
    children = graph.children(ref("dub"), "classification")
    assert children == set(map(ref, ["jamaican-dub", "french-dub", "british-dub"]))
    assert {graph.edge_kind(child, ref("dub")) for child in children} == {"expression"}


def test_e07_direct_coverage_and_scope_rules(payload):
    graph = GenreGraph(payload)
    assert ref("french-reggae-fusion") in graph.selected_nodes(ref("reggae"))
    assert ref("french-reggae-fusion") in graph.selected_nodes(ref("reggae"), scope="expressions")
    assert ref("french-reggae-fusion") not in graph.selected_nodes(ref("reggae"), scope="restricted")
    assert graph.selected_nodes(ref("dub"), include_descendants=False) == {ref("dub")}
    for scope in ("all", "canonical", "regional"):
        with pytest.raises(GraphValidationError, match="Invalid selection scope"):
            graph.selected_nodes(ref("france"), scope=scope)


def test_m01_e07_expression_descendants_share_only_the_scoped_population(payload):
    payload["nodes"].append(genre("local-dub-child"))
    payload["relations"].extend([relation("local-dub-child", "french-dub"), relation("local-dub-child", "dub")])
    graph = GenreGraph(payload)
    assert graph.state(ref("local-dub-child")) == "regional"
    assert graph.edge_kind(ref("local-dub-child"), ref("french-dub")) == "restricted"
    assert graph.edge_kind(ref("local-dub-child"), ref("dub")) == "expression"
    for parent in ("french-dub", "france", "world"):
        assert ref("local-dub-child") in graph.selected_nodes(ref(parent), scope="restricted")
    assert ref("local-dub-child") in graph.selected_nodes(ref("dub"))
    assert ref("local-dub-child") not in graph.selected_nodes(ref("dub"), scope="restricted")
    assert ref("local-dub-child") not in graph.selected_nodes(ref("jamaica"))
    assert graph.normalize_attributions(map(ref, ["local-dub-child", "french-dub", "france", "dub"])) == {
        ref("local-dub-child")
    }


def test_r03_r06_canonical_genre_transmits_its_expressions_to_regional_parents(payload):
    graph = GenreGraph(payload)
    assert graph.selected_nodes(ref("reggae-fusion")) == set(map(ref, ["reggae-fusion", "french-reggae-fusion"]))
    assert graph.selected_nodes(ref("reggae-fusion"), scope="restricted") == {ref("reggae-fusion")}
    assert ref("french-reggae-fusion") in graph.selected_nodes(ref("france"), scope="restricted")
    assert graph.normalize_attributions(map(ref, ["french-reggae-fusion", "france", "reggae-fusion"])) == {
        ref("french-reggae-fusion")
    }


def test_hip_hop_chain_widens_then_narrows_regions(payload):
    payload["nodes"].extend(
        [
            genre("hip-hop"),
            genre("european-hip-hop"),
            genre("french-rap"),
            genre("rap-marseillais"),
            overview("europe"),
            overview("marseille"),
        ]
    )
    payload["canonicalRoots"].append({"nodeId": ref("hip-hop"), "provenance": provenance("hip-hop-root")})
    payload["relations"].extend(
        [
            relation("europe", "world", "regional_membership"),
            relation("france", "europe", "regional_membership"),
            relation("marseille", "france", "regional_membership"),
            relation("european-hip-hop", "europe", "regional_membership"),
            relation("european-hip-hop", "hip-hop"),
            relation("french-rap", "france", "regional_membership"),
            relation("french-rap", "european-hip-hop"),
            relation("rap-marseillais", "marseille", "regional_membership"),
            relation("rap-marseillais", "french-rap"),
        ]
    )
    graph = GenreGraph(payload)
    assert graph.edge_kind(ref("european-hip-hop"), ref("hip-hop")) == "expression"
    assert graph.edge_kind(ref("french-rap"), ref("european-hip-hop")) == "restricted"
    assert graph.edge_kind(ref("rap-marseillais"), ref("french-rap")) == "restricted"
    chain = set(map(ref, ["european-hip-hop", "french-rap", "rap-marseillais"]))
    assert graph.selected_nodes(ref("hip-hop"), scope="restricted") == {ref("hip-hop")}
    assert graph.selected_nodes(ref("hip-hop"), scope="expressions") == chain
    assert graph.selected_nodes(ref("hip-hop")) == chain | {ref("hip-hop")}
    assert graph.selected_nodes(ref("european-hip-hop"), scope="restricted") == chain
    assert graph.selected_nodes(ref("french-rap"), scope="restricted") == set(
        map(ref, ["french-rap", "rap-marseillais"])
    )


def test_drill_expression_reaches_its_parent_but_not_the_parents_region(payload):
    payload["nodes"].extend([genre("drill"), genre("uk-drill"), genre("french-drill")])
    payload["canonicalRoots"].append({"nodeId": ref("drill"), "provenance": provenance("drill-root")})
    payload["relations"].extend(
        [
            relation("uk-drill", "britain", "regional_membership"),
            relation("uk-drill", "drill"),
            relation("french-drill", "france", "regional_membership"),
            relation("french-drill", "uk-drill"),
        ]
    )
    graph = GenreGraph(payload)
    assert graph.edge_kind(ref("french-drill"), ref("uk-drill")) == "expression"
    assert ref("french-drill") in graph.selected_nodes(ref("uk-drill"))
    assert ref("french-drill") not in graph.selected_nodes(ref("uk-drill"), scope="restricted")
    assert ref("french-drill") in graph.selected_nodes(ref("drill"))
    assert ref("french-drill") in graph.selected_nodes(ref("france"), scope="restricted")
    assert ref("french-drill") not in graph.selected_nodes(ref("britain"))


def test_expression_with_regional_population_selected_via_regional_root(payload):
    graph = GenreGraph(payload)
    assert graph.selected_nodes(ref("french-reggae"), scope="restricted") == set(
        map(ref, ["french-reggae", "french-reggae-child"])
    )
    assert ref("french-reggae-child") in graph.selected_nodes(ref("reggae"))
    assert ref("french-reggae-child") not in graph.selected_nodes(ref("reggae"), scope="restricted")
    assert ref("french-reggae-child") in graph.selected_nodes(ref("reggae"), scope="expressions")


def test_classified_regional_genre_is_an_expression_of_a_canonical_parent(payload):
    payload["relations"].append(relation("breton-rock", "country"))
    graph = GenreGraph(payload)
    assert graph.edge_kind(ref("breton-rock"), ref("country")) == "expression"
    assert graph.expression_parents(ref("breton-rock")) == {ref("country")}
    assert ref("breton-rock") in graph.selected_nodes(ref("country"), scope="expressions")


def test_r16_regional_membership_cycle_is_invalid(payload):
    payload["relations"].append(relation("world", "brittany", "regional_membership"))
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
    assert merged.parents(ref("jamaican-roots"), "classification") == {ref("dub")}
    assert merged.parents(ref("dub"), "classification") == {ref("reggae")}
    assert merged.state(ref("dub")) == "canonical"
    assert graph.node_ids >= {ref("roots")}


def test_merged_is_idempotent_and_ignores_a_missing_source(payload):
    merged = GenreGraph(payload).merged(ref("roots"), ref("dub"), merge_provenance())
    assert merged.merged(ref("roots"), ref("dub"), merge_provenance()) is merged


def test_merged_root_into_its_canonical_descendant_passes_rootship_on(payload):
    merged = GenreGraph(payload).merged(ref("reggae"), ref("dub"), merge_provenance())
    assert {root["nodeId"] for root in merged.to_payload()["canonicalRoots"]} == {ref("dub"), ref("country")}
    assert merged.parents(ref("roots"), "classification") == {ref("dub")}
    assert merged.parents(ref("dub"), "classification") == frozenset()
    assert all(merged.state(ref(key)) == "canonical" for key in ["dub", "roots", "reggae-fusion"])


def test_merged_rejects_a_root_that_would_become_a_regional_member(payload):
    with pytest.raises(GraphValidationError, match="Canonical root cannot be a regional member"):
        GenreGraph(payload).merged(ref("reggae"), ref("french-reggae"), merge_provenance())


def test_merged_rejects_a_merge_that_changes_the_state_of_another_node(payload):
    payload["nodes"].append(genre("sub-fusion"))
    payload["relations"].append(relation("sub-fusion", "reggae-fusion"))
    with pytest.raises(GraphValidationError, match="changes the state of") as caught:
        GenreGraph(payload).merged(ref("reggae-fusion"), ref("french-reggae"), merge_provenance())
    assert caught.value.paths == ((ref("sub-fusion"),),)


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


def test_d01_derivation_and_influence_are_inert(payload):
    before = GenreGraph(payload)
    payload["relations"].extend(
        [relation("dub", "french-reggae", "derivation"), relation("french-dub", "jamaican-dub", "influence")]
    )
    graph = GenreGraph(payload)
    assert graph.parents(ref("dub"), "derivation") == {ref("french-reggae")}
    assert graph.children(ref("french-reggae"), "derivation") == {ref("dub")}
    assert graph.parents(ref("french-dub"), "influence") == {ref("jamaican-dub")}
    for key in graph.node_ids:
        assert graph.state(key) == before.state(key)
        assert graph.selected_nodes(key) == before.selected_nodes(key)
    assert GenreGraph(graph.to_payload()).to_payload() == payload


def test_d01_contract_3_is_rejected(payload):
    payload["contractVersion"] = 3
    with pytest.raises(GraphValidationError, match="Invalid graph contract"):
        GenreGraph(payload)


@pytest.mark.parametrize("kind", ["derivation", "influence"])
@pytest.mark.parametrize(("child", "parent"), [("france", "dub"), ("dub", "france"), ("dub", "dub")])
def test_d02_invalid_descriptive_scope(payload, kind, child, parent):
    payload["relations"].append(relation(child, parent, kind))
    with pytest.raises(GraphValidationError, match=f"Invalid {kind} scope"):
        GenreGraph(payload)


@pytest.mark.parametrize("kind", ["derivation", "influence"])
def test_d02_descriptive_relation_duplicating_a_classification_is_rejected(payload, kind):
    payload["relations"].append(relation("dub", "reggae", kind))
    with pytest.raises(GraphValidationError, match="duplicates a classification relation"):
        GenreGraph(payload)


@pytest.mark.parametrize("kind", ["derivation", "influence"])
def test_d03_descriptive_cycle_is_rejected(payload, kind):
    payload["relations"] += [relation("dub", "french-dub", kind), relation("french-dub", "dub", kind)]
    with pytest.raises(GraphValidationError, match=f"Cycle in {kind}"):
        GenreGraph(payload)
