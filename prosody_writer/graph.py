"""Append-only DAG of alternating metrical positions.

Nodes are (syllable offset, previous position value); edges consume 1..max
syllables. Building another layer is constant work for fixed position limits.
Materializing all paths is still exponential, as in Prosodic's full parser.
"""
from .runtime import prosodic


class ScansionDAG:
    def __init__(self, max_s=2, max_w=2):
        if max_s < 1 or max_w < 1:
            raise ValueError("Position limits must be positive")
        self.limits = {"w": max_w, "s": max_s}
        self.length = 0
        self.edges = {(0, None): []}
        self.layers_added = 0
        self._paths = {}

    def extend_to(self, length):
        for end in range(self.length + 1, length + 1):
            for value, limit in self.limits.items():
                self.edges.setdefault((end, value), [])
                for size in range(1, min(limit, end) + 1):
                    start = end - size
                    previous = None if start == 0 else ("s" if value == "w" else "w")
                    self.edges.setdefault((start, previous), []).append((end, value * size))
            self.layers_added += 1
        self.length = max(self.length, length)

    def paths(self, length):
        self.extend_to(length)
        if length not in self._paths:
            def walk(offset, previous, prefix):
                # Match Prosodic's enumeration order, including tie breaking.
                edges = sorted(self.edges.get((offset, previous), []),
                               key=lambda e: (e[1][0] == "s", len(e[1])))
                for end, position in edges:
                    if end == length:
                        yield prefix + [position]
                for end, position in edges:
                    if end < length:
                        yield from walk(end, position[0], prefix + [position])
            self._paths[length] = list(walk(0, None, []))
        return self._paths[length]


class IncrementalMeter(prosodic.Meter):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dag = ScansionDAG(self.max_s, self.max_w)

    def get_possible_scansions(self, nsylls):
        return self.dag.paths(nsylls)
