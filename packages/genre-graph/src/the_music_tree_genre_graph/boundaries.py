"""Dependency-free canonical boundary evaluation, compatible with Python 3.12+."""

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


class GraphValidationError(ValueError):
    """An invalid complete graph, with bounded witness paths when available."""

    def __init__(self, message: str, *, paths: Iterable[Iterable[str]] = (), decisions: Iterable[str] = ()):
        super().__init__(message)
        self.paths = tuple(tuple(path) for path in paths)
        self.decisions = tuple(decisions)


def _cycle(parents: Mapping[str, Iterable[str]]) -> tuple[str, ...]:
    complete: set[str] = set()
    for start in parents:
        if start in complete:
            continue
        path = [start]
        active = {start: 0}
        pending = [iter(parents[start])]
        while pending:
            parent = next(pending[-1], None)
            if parent is None:
                finished = path.pop()
                complete.add(finished)
                del active[finished]
                pending.pop()
            elif parent in active:
                return (*path[active[parent] :], parent)
            elif parent not in complete:
                active[parent] = len(path)
                path.append(parent)
                pending.append(iter(parents[parent]))
    return ()


def topological_order(parents: Mapping[str, Iterable[str]], relation: str) -> tuple[str, ...]:
    parents = {node: frozenset(values) for node, values in parents.items()}
    children: dict[str, list[str]] = defaultdict(list)
    remaining = {node: len(tuple(ancestors)) for node, ancestors in parents.items()}
    for child, ancestors in parents.items():
        for parent in ancestors:
            children[parent].append(child)
    pending = deque(node for node in sorted(parents) if remaining[node] == 0)
    ordered = []
    while pending:
        parent = pending.popleft()
        ordered.append(parent)
        for child in sorted(children[parent]):
            remaining[child] -= 1
            if remaining[child] == 0:
                pending.append(child)
    if len(ordered) != len(parents):
        path = _cycle(parents)
        raise GraphValidationError(f"Cycle in {relation}: {' -> '.join(path)}", paths=[path])
    return tuple(ordered)


@dataclass(frozen=True)
class BoundaryResult:
    state: str
    inherited_state: str
    predecessor: str | None
    boundary_id: str | None


def boundary_witness(results: Mapping[str, BoundaryResult], node: str) -> tuple[str, ...]:
    path = []
    current: str | None = node
    while current is not None:
        path.append(current)
        current = results[current].predecessor
    return tuple(reversed(path))


def evaluate_boundaries(
    parents: Mapping[str, Iterable[str]], boundaries: Iterable[Mapping]
) -> dict[str, BoundaryResult]:
    """Resolve accepted classification edges without requiring precomputed node flags.

    Inputs contain genres only. A predecessor per node keeps successful evaluation
    linear in graph size; witness paths are expanded only for errors or inspection.
    """
    if boundaries is None:
        raise GraphValidationError("Missing boundary configuration")
    parents = {node: frozenset(values) for node, values in parents.items()}
    for node, values in parents.items():
        unknown = values - parents.keys()
        if unknown:
            raise GraphValidationError(f"Unknown classification parents of {node}: {sorted(unknown)}")
    order = topological_order(parents, "classification")
    decisions_by_node = {}
    for boundary in boundaries:
        if not isinstance(boundary, Mapping) or not {"nodeId", "type", "provenance"} <= boundary.keys():
            raise GraphValidationError("Invalid boundary: nodeId, type and provenance are required")
        provenance = boundary["provenance"]
        if not isinstance(provenance, Mapping) or any(
            not isinstance(provenance.get(key), str) or not provenance[key].strip()
            for key in ("decisionId", "source", "rationale")
        ):
            raise GraphValidationError("Invalid boundary provenance: decisionId, source and rationale are required")
        if boundary["type"] not in {"entry", "exit"}:
            raise GraphValidationError(f"Invalid boundary type: {boundary['type']}")
        node = boundary["nodeId"]
        if node not in parents:
            raise GraphValidationError(f"Unknown classification boundary node: {node}")
        if node in decisions_by_node:
            raise GraphValidationError(
                f"Multiple boundary decisions on {node}",
                decisions=[decisions_by_node[node]["provenance"]["decisionId"], boundary["provenance"]["decisionId"]],
            )
        decisions_by_node[node] = boundary
    results: dict[str, BoundaryResult] = {}
    transitions = {("before_entry", "entry"): "canonical", ("canonical", "exit"): "after_exit"}
    for node in order:
        node_parents = sorted(parents[node])
        predecessor = node_parents[0] if node_parents else None
        inherited = results[predecessor].state if predecessor else "before_entry"
        for other in node_parents[1:]:
            if results[other].state != inherited:
                witnesses = [(*boundary_witness(results, parent), node) for parent in (node_parents[0], other)]
                decisions = [results[parent].boundary_id for parent in (node_parents[0], other)]
                raise GraphValidationError(
                    f"Conflicting classification states at {node}: {inherited} / {results[other].state}",
                    paths=witnesses,
                    decisions=[decision for decision in decisions if decision is not None],
                )
        boundary_id = results[predecessor].boundary_id if predecessor else None
        state = inherited
        if boundary := decisions_by_node.get(node):
            decision_id = boundary["provenance"]["decisionId"]
            transition = inherited, boundary["type"]
            if transition not in transitions:
                path = (*boundary_witness(results, predecessor), node) if predecessor else (node,)
                raise GraphValidationError(
                    f"Invalid {boundary['type']} at {node} from {inherited}",
                    paths=[path],
                    decisions=[decision for decision in (boundary_id, decision_id) if decision is not None],
                )
            state, boundary_id = transitions[transition], decision_id
        results[node] = BoundaryResult(state, inherited, predecessor, boundary_id)
    return results
