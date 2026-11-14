"""Validate semantic relations before deriving presentation, membership or provenance."""

import json
from collections.abc import Iterable, Mapping
from copy import deepcopy
from functools import cache
from importlib.resources import files
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from .boundaries import GraphValidationError, boundary_witness, evaluate_boundaries, topological_order


@cache
def _schema_validator() -> Draft202012Validator:
    return Draft202012Validator(load_genre_graph_schema(), format_checker=FormatChecker())


def load_genre_graph_schema() -> dict:
    resource = files("the_music_tree_genre_kit") / "schemas" / "genre_graph.schema.json"
    return json.loads(resource.read_text(encoding="utf-8"))


class GenreGraph:
    """An immutable validated snapshot. All edges point from child to parent.

    Only classification propagates boundary state. Only regional membership
    propagates a regional population. Expression associations allow canonical
    access in one direction; anchors never propagate songs.
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
            kind: {node: set() for node in self._nodes}
            for kind in ("classification", "regional_membership", "expression_style", "anchoring")
        }
        self._index_relations()
        classification = self._relations["classification"]
        self.classification_order = topological_order(classification, "classification")
        self.regional_order = topological_order(self._relations["regional_membership"], "regional membership")
        genre_parents = {
            node: values for node, values in classification.items() if self._nodes[node]["kind"] == "genre"
        }
        self.boundary_results = MappingProxyType(evaluate_boundaries(genre_parents, self._payload["boundaries"]))
        for node, result in self.boundary_results.items():
            if self._nodes[node]["canonicalState"] != result.state:
                raise GraphValidationError(f"Contradictory canonicalState on {node}: expected {result.state}")
        self._validate_semantics()
        self._children: dict[str, dict[str, frozenset[str]]] = {}
        for kind, parents in self._relations.items():
            children: dict[str, set[str]] = {node: set() for node in self._nodes}
            for child, ancestors in parents.items():
                for parent in ancestors:
                    children[parent].add(child)
            self._children[kind] = {node: frozenset(values) for node, values in children.items()}
        self._validate_overviews()
        self._index_population()

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
                "regional_membership": child_kind != "overview" or parent_kind == "overview",
                "expression_style": child_kind == "expression" and parent_kind == "genre",
                "anchoring": child_kind == "genre" and parent_kind == "overview",
            }[kind]
            if not valid:
                raise GraphValidationError(f"Invalid {kind} scope: {child} -> {parent}")

    def boundary_witness(self, node_id: str) -> tuple[str, ...]:
        return boundary_witness(self.boundary_results, node_id)

    def _validate_semantics(self) -> None:
        regional_parents = {parent for parents in self._relations["regional_membership"].values() for parent in parents}
        for node, data in self._nodes.items():
            canonical = data["kind"] == "genre" and self.boundary_results[node].state == "canonical"
            if canonical and (self._relations["regional_membership"][node] or node in regional_parents):
                raise GraphValidationError(
                    f"Canonical population cannot be a regional member: {node}; use an expression"
                )
            if data["kind"] == "expression" and not self._relations["expression_style"][node]:
                raise GraphValidationError(f"Expression lacks a canonical style: {node}")
            for style in self._relations["expression_style"][node]:
                if self.boundary_results[style].state != "canonical":
                    raise GraphValidationError(f"Expression style must be canonical: {node} -> {style}")
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

    def _index_population(self) -> None:
        # Crossing from a before-entry prefix into a canonical interval never
        # transmits that style's worldwide population to the prefix's regions.
        canonical = {node for node, result in self.boundary_results.items() if result.state == "canonical"}
        population = {node: set(parents) for node, parents in self._relations["regional_membership"].items()}
        access = {node: set(parents) for node, parents in population.items()}
        for node, parents in self._relations["classification"].items():
            population[node].update(parent for parent in parents if node not in canonical and parent not in canonical)
            access[node].update(parent for parent in parents if parent in canonical or node not in canonical)
        for node, styles in self._relations["expression_style"].items():
            access[node].update(styles)
        for kind, parents in (("population", population), ("access", access)):
            topological_order(parents, kind)
            self._relations[kind] = parents
            children = {node: set() for node in self._nodes}
            for child, values in parents.items():
                for parent in values:
                    children[parent].add(child)
            self._children[kind] = {node: frozenset(values) for node, values in children.items()}

    def selected_nodes(self, node_id: str, *, scope: str = "all", include_descendants: bool = True) -> frozenset[str]:
        """Select semantic populations; stop regional access at canonical entries.

        Canonical scope covers canonical classification descendants and complete
        associated expression populations. Regional scope covers those expression
        populations and exited classification descendants. All scopes retain the
        selected style itself, matching the existing HTTP contract.
        """
        node = self._nodes[node_id]
        canonical = node["kind"] == "genre" and self.boundary_results[node_id].state == "canonical"
        if scope not in {"canonical", "regional", "all"} or (not canonical and scope != "all"):
            raise GraphValidationError(f"Invalid selection scope {scope} for {node_id}")
        if not include_descendants:
            return frozenset({node_id})
        if not canonical:
            return frozenset({node_id}) | self.descendants(node_id, "population")
        classified = self.descendants(node_id, "classification") | {node_id}
        canonical_nodes = {node for node in classified if self.boundary_results[node].state == "canonical"}
        expressions = {
            expression for style in canonical_nodes for expression in self.children(style, "expression_style")
        }
        expression_population = set(expressions)
        for expression in expressions:
            expression_population.update(self.descendants(expression, "population"))
        if scope == "canonical":
            return frozenset(canonical_nodes | expression_population)
        regional = set(classified) - canonical_nodes
        for descendant in tuple(regional):
            regional.update(self.descendants(descendant, "population"))
        regional.update(expression_population)
        regional.add(node_id)
        return frozenset(regional if scope == "regional" else canonical_nodes | regional)

    def normalize_attributions(self, node_ids: Iterable[str]) -> frozenset[str]:
        """Remove ancestors only when inclusive selection preserves their access."""
        direct = frozenset(node_ids)
        unknown = direct - self.node_ids
        if unknown:
            raise GraphValidationError(f"Unknown attribution nodes: {sorted(unknown)}")
        redundant = set()
        for node in direct:
            redundant.update(self.ancestors(node, "access"))
        return direct - redundant

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

    def ancestry_subgraph(self, node_id: str) -> dict:
        """Share ancestor nodes instead of enumerating every regional path."""
        reachable = self.ancestors(node_id, "population") | {node_id}
        return {
            "nodes": [self.node(node) for node in sorted(reachable)],
            "relations": [
                deepcopy(edge)
                for edge in self._payload["relations"]
                if edge["type"] in {"classification", "regional_membership"}
                and edge["childId"] in reachable
                and edge["parentId"] in self._relations["population"][edge["childId"]]
            ],
        }
