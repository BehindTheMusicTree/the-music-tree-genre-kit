"""Validate semantic relations before deriving presentation, membership or provenance."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from copy import deepcopy
from functools import cache
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from .validation import GraphValidationError, topological_order


@cache
def _schema_validator() -> Draft202012Validator:
    return Draft202012Validator(load_genre_graph_schema(), format_checker=FormatChecker())


def load_genre_graph_schema() -> dict:
    resource = files("the_music_tree_genre_graph") / "genre_graph.schema.json"
    return json.loads(resource.read_text(encoding="utf-8"))


RELATION_TYPES = ("classification", "regional_membership", "derivation", "influence")
SELECTION_SCOPES = ("restricted", "extended", "expressions")


class GenreGraph:
    """An immutable validated snapshot. All edges point from child to parent.

    Lineage is a single relation, ``classification``. Each genre has regions (``regions``):
    its own overviews by ``regional_membership`` or, when it has none, those inherited from its
    regional classification parents. A genre with regions is regional; without, it is canonical
    and must descend from a listed root. A classification edge is computed as restricted (the
    child stays inside the parent's region) or an expression (the child leaves it, or a regional
    genre sits under a canonical one). ``derivation`` and ``influence`` are descriptive only.
    """

    def __init__(self, payload: dict[str, Any]):
        try:
            _schema_validator().validate(payload)
        except ValidationError as error:
            path = ".".join(str(part) for part in error.absolute_path)
            raise GraphValidationError(f"Invalid graph contract at {path or '<root>'}: {error.message}") from error
        self._payload = deepcopy(payload)
        self._nodes: dict[str, dict] = {}
        for node in self._payload["nodes"]:
            if node["id"] in self._nodes:
                raise GraphValidationError(f"Duplicate node identity: {node['id']}")
            self._nodes[node["id"]] = node
        self._relations: dict[str, dict[str, set[str]]] = {
            kind: {node: set() for node in self._nodes} for kind in RELATION_TYPES
        }
        self._index_relations()
        classification = self._relations["classification"]
        self.classification_order = topological_order(classification, "classification")
        self.regional_order = topological_order(self._relations["regional_membership"], "regional membership")
        derivation = self._relations["derivation"]
        influence = self._relations["influence"]
        topological_order(derivation, "derivation")
        topological_order(influence, "influence")
        for child, parents in influence.items():
            for parent in sorted(parents & (classification[child] | derivation[child])):
                raise GraphValidationError(
                    f"Influence is already implied by classification or derivation: {child} -> {parent}",
                    paths=[(child, parent)],
                )
        self._index_regional_ancestors()
        self._index_roots()
        self._index_regions()
        self._validate_display_parents()
        self._children: dict[str, dict[str, frozenset[str]]] = {}
        for kind, parents in self._relations.items():
            children: dict[str, set[str]] = {node: set() for node in self._nodes}
            for child, ancestors in parents.items():
                for parent in ancestors:
                    children[parent].add(child)
            self._children[kind] = {node: frozenset(values) for node, values in children.items()}
        self._validate_overviews()
        self._index_restricted()
        self._index_access()

    @property
    def node_ids(self) -> frozenset[str]:
        return frozenset(self._nodes)

    def node(self, node_id: str) -> dict:
        return deepcopy(self._nodes[node_id])

    def to_payload(self) -> dict:
        return deepcopy(self._payload)

    def parents(self, node_id: str, relation: str) -> frozenset[str]:
        return frozenset(self._relations[relation][node_id])

    def children(self, node_id: str, relation: str) -> frozenset[str]:
        return self._children[relation][node_id]

    def _index_relations(self) -> None:
        for relation in self._payload["relations"]:
            child, parent, kind = relation["childId"], relation["parentId"], relation["type"]
            if child not in self._nodes or parent not in self._nodes:
                raise GraphValidationError(f"Missing {kind} reference: {child} -> {parent}")
            if parent in self._relations[kind][child]:
                raise GraphValidationError(f"Duplicate {kind} relation: {child} -> {parent}")
            self._relations[kind][child].add(parent)
            child_kind, parent_kind = self._nodes[child]["kind"], self._nodes[parent]["kind"]
            valid = {
                "classification": child_kind == parent_kind == "genre",
                "regional_membership": parent_kind == "overview",
                "derivation": child != parent and child_kind == parent_kind == "genre",
                "influence": child != parent and child_kind == parent_kind == "genre",
            }[kind]
            if not valid:
                raise GraphValidationError(f"Invalid {kind} scope: {child} -> {parent}")

    def state(self, node_id: str) -> str | None:
        """``canonical`` or ``regional`` for a genre, ``None`` for an overview."""
        return self._state.get(node_id)

    def regions(self, node_id: str) -> frozenset[str]:
        """The overviews a genre belongs to: its own, or those inherited from its regional parents."""
        return self._regions.get(node_id, frozenset())

    def edge_kind(self, child: str, parent: str) -> str:
        """``restricted`` or ``expression`` for a classification edge."""
        try:
            return self._edge_kind[(child, parent)]
        except KeyError:
            raise GraphValidationError(f"Not a classification relation: {child} -> {parent}") from None

    def expression_parents(self, node_id: str) -> frozenset[str]:
        """Classification parents this node is a regional expression of."""
        return frozenset(
            parent
            for parent in self._relations["classification"][node_id]
            if self._edge_kind[(node_id, parent)] == "expression"
        )

    def _index_regional_ancestors(self) -> None:
        regional = self._relations["regional_membership"]
        found: dict[str, frozenset[str]] = {}
        for node in self.regional_order:
            above: set[str] = set()
            for parent in regional[node]:
                above.add(parent)
                above.update(found[parent])
            found[node] = frozenset(above)
        self._regional_ancestors = found

    def _inside(self, region: str, other: str) -> bool:
        """``region`` is ``other`` or lies below it by regional membership."""
        return region == other or other in self._regional_ancestors[region]

    def _most_specific(self, regions: set[str]) -> frozenset[str]:
        return frozenset(
            region
            for region in regions
            if not any(other != region and region in self._regional_ancestors[other] for other in regions)
        )

    def _index_roots(self) -> None:
        roots: set[str] = set()
        for root in self._payload["canonicalRoots"]:
            node = root["nodeId"]
            if node not in self._nodes:
                raise GraphValidationError(f"Unknown canonical root: {node}")
            if node in roots:
                raise GraphValidationError(f"Duplicate canonical root: {node}")
            if self._nodes[node]["kind"] != "genre":
                raise GraphValidationError(f"Canonical root is not a genre: {node}")
            if self._relations["classification"][node]:
                raise GraphValidationError(f"Canonical root has a classification parent: {node}")
            if self._relations["regional_membership"][node]:
                raise GraphValidationError(f"Canonical root cannot be a regional member: {node}")
            roots.add(node)
        self._roots = frozenset(roots)

    def _index_regions(self) -> None:
        """Regions, state and edge kinds, computed parents first."""
        classification = self._relations["classification"]
        regional = self._relations["regional_membership"]
        regions: dict[str, frozenset[str]] = {}
        state: dict[str, str] = {}
        edge_kind: dict[tuple[str, str], str] = {}
        for node in self.classification_order:
            if self._nodes[node]["kind"] != "genre":
                continue
            parents = sorted(classification[node])
            own = regional[node]
            if own:
                found = frozenset(own)
            else:
                found = self._most_specific({region for parent in parents for region in regions[parent]})
            regions[node] = found
            if found:
                state[node] = "regional"
            elif node in self._roots or (parents and all(state[parent] == "canonical" for parent in parents)):
                state[node] = "canonical"
            else:
                raise GraphValidationError(f"Genre without region or canonical root: {node}", paths=[(node,)])
            for parent in parents:
                kind = self._boundary(node, parent, own_regions=bool(own), regions=regions, state=state)
                edge_kind[(node, parent)] = kind
        self._regions, self._state, self._edge_kind = regions, state, edge_kind

    def _boundary(self, node, parent, *, own_regions, regions, state) -> str:
        if state[node] == "canonical":
            return "restricted"
        if state[parent] == "canonical":
            return "expression"
        if not own_regions:
            return "restricted"
        child_regions, parent_regions = regions[node], regions[parent]
        if all(any(self._inside(region, other) for other in parent_regions) for region in child_regions):
            return "restricted"
        if all(
            any(region != other and self._inside(other, region) for other in parent_regions) for region in child_regions
        ):
            raise GraphValidationError(
                f"Genre is broader than its classification parent: {node} -> {parent}", paths=[(node, parent)]
            )
        return "expression"

    def _validate_display_parents(self) -> None:
        for node, data in self._nodes.items():
            if parent := data.get("displayParentId"):
                transmitting = self._relations["classification"][node] | self._relations["regional_membership"][node]
                if parent not in transmitting:
                    raise GraphValidationError(f"Display parent is not an accepted parent: {node} -> {parent}")

    def _validate_overviews(self) -> None:
        for node, data in self._nodes.items():
            if data["kind"] == "overview":
                expected = data["overviewType"] == "current" or bool(self.children(node, "regional_membership"))
                if data["isUmbrella"] != expected:
                    raise GraphValidationError(f"Contradictory isUmbrella on {node}: expected {expected}")

    def ancestors(self, node_id: str, relation: str) -> frozenset[str]:
        found: set[str] = set()
        pending = [node_id]
        while pending:
            for parent in self._relations[relation][pending.pop()]:
                if parent not in found:
                    found.add(parent)
                    pending.append(parent)
        return frozenset(found)

    def descendants(self, node_id: str, relation: str) -> frozenset[str]:
        found: set[str] = set()
        pending = [node_id]
        while pending:
            for child in self.children(pending.pop(), relation):
                if child not in found:
                    found.add(child)
                    pending.append(child)
        return frozenset(found)

    def _index_restricted(self) -> None:
        """Population and regions only climb regional membership and restricted classification edges."""
        restricted = {node: set(parents) for node, parents in self._relations["regional_membership"].items()}
        for (child, parent), kind in self._edge_kind.items():
            if kind == "restricted":
                restricted[child].add(parent)
        topological_order(restricted, "restricted")
        self._relations["restricted"] = restricted
        children: dict[str, set[str]] = {node: set() for node in self._nodes}
        for child, parents in restricted.items():
            for parent in parents:
                children[parent].add(child)
        self._children["restricted"] = {node: frozenset(values) for node, values in children.items()}

    def _index_access(self) -> None:
        """Access climbs every classification edge, then the regions of the node and their ancestors.

        An expression therefore reaches the lineage of its parent but never the parent's regions.
        Ancestors are computed once, parents first.
        """
        classification = self._relations["classification"]
        lineage: dict[str, frozenset[str]] = {}
        for node in self.classification_order:
            found: set[str] = set()
            for parent in classification[node]:
                found.add(parent)
                found.update(lineage[parent])
            lineage[node] = frozenset(found)
        access: dict[str, frozenset[str]] = {}
        for node in self._nodes:
            found = set(lineage[node])
            if self._nodes[node]["kind"] == "genre":
                for region in self._regions[node]:
                    found.add(region)
                    found.update(self._regional_ancestors[region])
            else:
                found.update(self._regional_ancestors[node])
            access[node] = frozenset(found)
        self._access_ancestors = access
        descendants: dict[str, set[str]] = {node: set() for node in self._nodes}
        for node, ancestors in access.items():
            for ancestor in ancestors:
                descendants[ancestor].add(node)
        self._access_descendants = {node: frozenset(values) for node, values in descendants.items()}

    def selected_nodes(
        self, node_id: str, *, scope: str = "extended", include_descendants: bool = True
    ) -> frozenset[str]:
        """Select a node and everything that reaches it by access.

        ``restricted`` covers the node and its descendants by regional membership and restricted
        classification edges that also reach the node by access; ``extended`` every descendant by access; ``expressions`` what
        ``extended`` adds to ``restricted``, without the node itself (so empty without descendants).
        """
        if scope not in SELECTION_SCOPES or node_id not in self._nodes:
            raise GraphValidationError(f"Invalid selection scope {scope} for {node_id}")
        if not include_descendants:
            return frozenset() if scope == "expressions" else frozenset({node_id})
        extended = self._access_descendants[node_id] | {node_id}
        if scope == "extended":
            return extended
        restricted = (self.descendants(node_id, "restricted") | {node_id}) & extended
        return restricted if scope == "restricted" else extended - restricted

    def normalize_attributions(self, node_ids: Iterable[str]) -> frozenset[str]:
        """Remove ancestors only when inclusive selection preserves their access."""
        direct = frozenset(node_ids)
        unknown = direct - self.node_ids
        if unknown:
            raise GraphValidationError(f"Unknown attribution nodes: {sorted(unknown)}")
        # Access is not transitive (an expression reaches its parent's lineage but not its regions), so a node is
        # dropped only when the survivors still cover it and everything above it.
        # Dropping the topmost nodes first keeps the result independent of input order.
        covers = {node: self._access_ancestors[node] | {node} for node in direct}
        counts = Counter(member for cover in covers.values() for member in cover)
        kept = set(direct)
        for node in sorted(direct, key=lambda item: (len(self._access_ancestors[item]), item)):
            if all(counts[member] > 1 for member in covers[node]):
                kept.discard(node)
                counts.subtract(covers[node])
        return frozenset(kept)

    def refinement_nodes(self, node_ids: Iterable[str]) -> frozenset[str]:
        return frozenset(
            node for node in self.normalize_attributions(node_ids) if self._nodes[node].get("isUmbrella", False)
        )

    def reduced_regional_relations(self) -> frozenset[tuple[str, str]]:
        """Return the unique DAG reduction using only accepted regional membership."""
        result = set()
        for child, parents in self._relations["regional_membership"].items():
            redundant = set()
            for parent in parents:
                redundant.update(self.ancestors(parent, "regional_membership"))
            result.update((child, parent) for parent in parents - redundant)
        return frozenset(result)

    def merged(self, source: str, target: str, provenance: Mapping[str, str]) -> GenreGraph:
        """Return the graph where ``source`` is absorbed by ``target``.

        Idempotent: once ``source`` is gone the graph is returned unchanged. Relations and
        display parents of ``source`` move to ``target``. A merge may not change the canonical
        state of any other node; a root merged into its descendant passes its rootship on.
        """
        if target not in self._nodes:
            raise GraphValidationError(f"Unknown merge target: {target}")
        if source not in self._nodes:
            return self
        if source == target:
            raise GraphValidationError(f"Cannot merge a node into itself: {source}")
        if self._nodes[source]["kind"] != self._nodes[target]["kind"]:
            raise GraphValidationError(f"Cannot merge nodes of different kinds: {source} -> {target}")
        payload = self.to_payload()

        def remap(node: str) -> str:
            return target if node == source else node

        def key(relation: dict) -> tuple[str, str, str]:
            return relation["childId"], relation["parentId"], relation["type"]

        untouched = {key(r) for r in payload["relations"] if source not in (r["childId"], r["parentId"])}
        relations: list[dict] = []
        seen = set(untouched)
        for relation in payload["relations"]:
            if source in (relation["childId"], relation["parentId"]):
                relation = {**relation, "childId": remap(relation["childId"]), "parentId": remap(relation["parentId"])}
                if relation["childId"] == relation["parentId"] or key(relation) in seen:
                    continue
                seen.add(key(relation))
            relations.append(relation)
        source_display = self._nodes[source].get("displayParentId")
        nodes = []
        for node in payload["nodes"]:
            if node["id"] == source:
                continue
            if node.get("displayParentId") == source:
                if node["id"] == target and source_display and source_display != target:
                    node["displayParentId"] = source_display
                elif node["id"] == target:
                    del node["displayParentId"]
                else:
                    node["displayParentId"] = target
            if node["id"] == target and node["kind"] == "overview":
                node["isUmbrella"] = node["overviewType"] == "current" or any(
                    r["type"] == "regional_membership" and r["parentId"] == target for r in relations
                )
            nodes.append(node)
        roots = [root for root in payload["canonicalRoots"] if root["nodeId"] != source]
        if source in self._roots:
            if all(root["nodeId"] != target for root in roots):
                roots.append({"nodeId": target, "provenance": dict(provenance)})
        merged = GenreGraph({**payload, "nodes": nodes, "relations": relations, "canonicalRoots": roots})
        changed = sorted(node for node in merged.node_ids if node != source and merged.state(node) != self.state(node))
        if changed:
            raise GraphValidationError(
                f"Merging {source} into {target} changes the state of: {changed}", paths=[tuple(changed)]
            )
        return merged

    def ancestry_subgraph(self, node_id: str) -> dict:
        """Share ancestor nodes instead of enumerating every regional path."""
        reachable = self.ancestors(node_id, "restricted") | {node_id}
        return {
            "nodes": [self.node(node) for node in sorted(reachable)],
            "relations": [
                deepcopy(edge)
                for edge in self._payload["relations"]
                if edge["type"] in {"classification", "regional_membership"}
                and edge["childId"] in reachable
                and edge["parentId"] in self._relations["restricted"][edge["childId"]]
            ],
        }
