"""Dependency-free graph validation primitives, compatible with Python 3.12+."""

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping


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
