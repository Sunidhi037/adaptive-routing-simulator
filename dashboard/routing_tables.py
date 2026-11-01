"""Step-by-step Dijkstra / Bellman-Ford traces and the tables built from them.

Self-contained on purpose (no import of ``routing_engine``): the dashboard
computes its own *visualisation trace* from the topology JSON. Each ``Step`` is
a snapshot of the algorithm after one action, so the UI can show the distance
table and the routing table at any step.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from graph_model import Topology, fmt_cost, natural_key

INF = math.inf
DIJKSTRA = "Dijkstra"
BELLMAN_FORD = "Bellman-Ford"
ALGORITHMS = (DIJKSTRA, BELLMAN_FORD)
_MAX_LINES = 12  # keep the explanation panel readable


@dataclass
class Step:
    index: int
    title: str
    explanation: str
    source: str
    dist: dict[str, float]
    prev: dict[str, str | None]
    state: dict[str, str]  # final | tentative | unreached | down
    current: str | None = None  # Dijkstra: router finalised in this step
    updated: list[str] = field(default_factory=list)  # routers whose distance improved in this step
    updated_edges: list[tuple[str, str]] = field(default_factory=list)  # (from, to) that caused the improvement
    is_last: bool = False


# ---- helpers ------------------------------------------------------------------
def _states(routers, dist, finalised, down) -> dict[str, str]:
    out = {}
    for r in routers:
        if r in down:
            out[r] = "down"
        elif r in finalised:
            out[r] = "final"
        elif dist[r] < INF:
            out[r] = "tentative"
        else:
            out[r] = "unreached"
    return out


def _snapshot(index, title, explanation, source, routers, dist, prev, finalised, down, **extra) -> Step:
    return Step(index=index, title=title, explanation=explanation, source=source, dist=dict(dist), prev=dict(prev),
                state=_states(routers, dist, finalised, down), **extra)


def _unreachable_note(routers, dist, down, source) -> str:
    lost = [r for r in routers if r not in down and dist[r] == INF]
    parts = []
    if lost:
        parts.append(f"Unreachable from {source}: **{', '.join(lost)}**.")
    else:
        parts.append(f"Every active router is reachable from {source}.")
    if down:
        parts.append(f"Routers that are down: {', '.join(sorted(down, key=natural_key))}.")
    return " ".join(parts)


def _source_down_trace(topo, source, routers) -> list[Step]:
    dist = {r: INF for r in routers}
    prev = {r: None for r in routers}
    return [_snapshot(0, "Source router is down", f"Source router **{source}** has failed, so no routes can be computed. "
                      "Recover it from the sidebar to continue.", source, routers, dist, prev, set(), set(topo.failed_routers),
                      is_last=True)]


def path_to(prev: dict[str, str | None], source: str, dest: str) -> list[str]:
    """Follow predecessor pointers back to the source; [] if no route is known (yet)."""
    if dest == source:
        return [source]
    path, seen = [dest], {dest}
    while path[-1] != source:
        parent = prev.get(path[-1])
        if parent is None or parent in seen:
            return []
        path.append(parent)
        seen.add(parent)
    return path[::-1]


# ---- Dijkstra -----------------------------------------------------------------
def dijkstra_trace(topo: Topology, source: str) -> list[Step]:
    routers = sorted(topo.routers, key=natural_key)
    down = set(topo.failed_routers)
    if source in down:
        return _source_down_trace(topo, source, routers)

    dist = {r: INF for r in routers}
    prev: dict[str, str | None] = {r: None for r in routers}
    dist[source] = 0.0
    visited: set[str] = set()
    steps = [_snapshot(0, "Initialisation",
                       f"Distance to the source **{source}** is 0; every other router starts at ∞. Nothing is final yet.",
                       source, routers, dist, prev, visited, down)]

    while True:
        candidates = [r for r in routers if r not in visited and r not in down and dist[r] < INF]
        if not candidates:
            break
        u = min(candidates, key=lambda r: (dist[r], natural_key(r)))
        visited.add(u)
        lines, skipped, updated, edges = [], [], [], []
        for v, w in sorted(topo.neighbors(u).items(), key=lambda kv: natural_key(kv[0])):
            if v in visited:
                skipped.append(v)
                continue
            candidate = dist[u] + w
            if candidate < dist[v]:
                lines.append(f"- **{v}**: {fmt_cost(dist[u])} + {fmt_cost(w)} = {fmt_cost(candidate)} < {fmt_cost(dist[v])} → **updated** (via {u})")
                dist[v], prev[v] = candidate, u
                updated.append(v)
                edges.append((u, v))
            else:
                lines.append(f"- {v}: {fmt_cost(dist[u])} + {fmt_cost(w)} = {fmt_cost(candidate)} ≥ {fmt_cost(dist[v])} → keep")
        text = (f"Pick **{u}**: the unfinalised router with the smallest distance ({fmt_cost(dist[u])}). Its distance is now final.\n\n"
                + ("Relax its links:\n" + "\n".join(lines) if lines else "No outgoing links left to relax."))
        if skipped:
            text += f"\n\n_Skipped (already final): {', '.join(skipped)}._"
        steps.append(_snapshot(len(steps), f"Finalise {u}", text, source, routers, dist, prev, visited, down,
                               current=u, updated=updated, updated_edges=edges))

    steps.append(_snapshot(len(steps), "Done", "No router with a finite distance is left to process. "
                           + _unreachable_note(routers, dist, down, source), source, routers, dist, prev, visited, down, is_last=True))
    return steps


# ---- Bellman-Ford -------------------------------------------------------------
def bellman_ford_trace(topo: Topology, source: str) -> list[Step]:
    routers = sorted(topo.routers, key=natural_key)
    down = set(topo.failed_routers)
    if source in down:
        return _source_down_trace(topo, source, routers)

    active = [r for r in routers if r not in down]
    edges = [(u, v, w) for u in active for v, w in sorted(topo.neighbors(u).items(), key=lambda kv: natural_key(kv[0]))]
    dist = {r: INF for r in routers}
    prev: dict[str, str | None] = {r: None for r in routers}
    dist[source] = 0.0
    steps = [_snapshot(0, "Initialisation",
                       f"Distance to the source **{source}** is 0; every other router starts at ∞. "
                       f"Bellman-Ford will relax **every** active link (in both directions) up to {max(len(active) - 1, 0)} times.",
                       source, routers, dist, prev, {source}, down)]

    converged = False
    iterations_run = 0
    for iteration in range(1, len(active)):
        iterations_run = iteration
        lines, last_edge, updated = [], {}, []
        for u, v, w in edges:
            if dist[u] < INF and dist[u] + w < dist[v]:
                lines.append(f"- {u} → {v}: {fmt_cost(dist[u])} + {fmt_cost(w)} = {fmt_cost(dist[u] + w)} < {fmt_cost(dist[v])} → **{v} updated**")
                dist[v], prev[v] = dist[u] + w, u
                last_edge[v] = (u, v)
                if v not in updated:
                    updated.append(v)
        converged = not updated
        if converged:
            text = "Every link was checked and **no distance changed**, so the distances are stable and the algorithm can stop early."
        else:
            shown = lines[:_MAX_LINES] + ([f"- … and {len(lines) - _MAX_LINES} more"] if len(lines) > _MAX_LINES else [])
            text = f"All active links were relaxed once. **{len(updated)} router(s) improved**:\n" + "\n".join(shown)
        title = f"Iteration {iteration}" + (" – no change (converged)" if converged else "")
        steps.append(_snapshot(len(steps), title, text, source, routers, dist, prev, {source}, down,
                               updated=updated, updated_edges=list(last_edge.values())))
        if converged:
            break

    finalised = {r for r in active if dist[r] < INF}
    how = ("It stopped early because the distances stopped changing." if converged
           else f"It completed the maximum of V − 1 = {max(len(active) - 1, 0)} iterations.")
    steps.append(_snapshot(len(steps), "Done", f"{how} Negative-cycle check: every link cost is ≥ 0, so there is no negative cycle. "
                           + _unreachable_note(routers, dist, down, source), source, routers, dist, prev, finalised, down,
                           is_last=True))
    return steps


def run_algorithm(name: str, topo: Topology, source: str) -> list[Step]:
    if name == DIJKSTRA:
        return dijkstra_trace(topo, source)
    if name == BELLMAN_FORD:
        return bellman_ford_trace(topo, source)
    raise ValueError(f"Unknown algorithm: {name!r}")


# ---- tables -------------------------------------------------------------------
def distance_rows(step: Step) -> list[dict[str, str]]:
    labels = {"final": "Final", "tentative": "Tentative", "down": "Router down",
              "unreached": "Unreachable" if step.is_last else "Not reached yet"}
    rows = []
    for router in sorted(step.dist, key=natural_key):
        note = []
        if router == step.source:
            note.append("source")
        if router == step.current:
            note.append("◀ finalised now")
        if router in step.updated:
            note.append("🔄 improved")
        rows.append({"Router": router,
                     "Distance": "—" if step.state[router] == "down" else fmt_cost(step.dist[router]),
                     "Previous hop": step.prev[router] or "—",
                     "State": labels[step.state[router]],
                     "Note": ", ".join(note)})
    return rows


def _entry(step: Step, dest: str):
    if step.state[dest] == "down":
        return (None, None, [])
    path = path_to(step.prev, step.source, dest) if step.dist[dest] < INF else []
    return (step.dist[dest], path[1] if len(path) > 1 else None, path)


def routing_rows(step: Step, previous: Step | None = None) -> list[dict[str, str]]:
    """Routing table of the source router at this step, with a 'Change' column vs. the previous step."""
    rows = []
    for dest in sorted(step.dist, key=natural_key):
        cost, hop, path = _entry(step, dest)
        if step.state[dest] == "down":
            status = "Router down"
        elif dest == step.source:
            status = "Local"
        elif cost == INF:
            status = "Unreachable" if step.is_last else "No route yet"
        else:
            status = "Final" if step.state[dest] == "final" else "Tentative"
        change = ""
        if previous is not None:
            old_cost, old_hop, _ = _entry(previous, dest)
            if (old_cost, old_hop) != (cost, hop):
                change = "🆕 new route" if old_cost == INF else "🔄 updated"
        rows.append({"Destination": dest, "Next hop": hop or "—",
                     "Cost": "—" if step.state[dest] == "down" else fmt_cost(cost),
                     "Path": " → ".join(path) if path else "—", "Status": status, "Change": change})
    return rows


# ---- route summary ------------------------------------------------------------
@dataclass
class RouteSummary:
    algorithm: str
    source: str
    destination: str
    reachable: bool
    path: list[str]
    total_cost: float | None
    message: str
    healthy_cost: float | None = None  # cost if every failure were recovered (None = still unreachable)

    def to_dict(self) -> dict:
        """Same keys/shape as RouteResult.to_dict() in routing_engine, so the outputs are interchangeable."""
        return {"source": self.source, "destination": self.destination,
                "status": "ok" if self.reachable else "unreachable", "reachable": self.reachable,
                "path": self.path, "total_cost": self.total_cost}


def summarize_route(algorithm: str, topo: Topology, source: str, destination: str, steps: list[Step] | None = None) -> RouteSummary:
    steps = steps or run_algorithm(algorithm, topo, source)
    final = steps[-1]
    healthy = run_algorithm(DIJKSTRA, topo.healthy(), source)[-1].dist.get(destination, INF)
    healthy_cost = None if healthy == INF else healthy
    cost = final.dist[destination]
    if cost < INF and final.state[destination] != "down":
        path = path_to(final.prev, source, destination)
        message = f"Shortest active route found with total cost {fmt_cost(cost)}."
        if healthy_cost is not None and cost > healthy_cost:
            message += f" Failures add {fmt_cost(cost - healthy_cost)} compared with the healthy network ({fmt_cost(healthy_cost)})."
        return RouteSummary(algorithm, source, destination, True, path, cost, message, healthy_cost)
    if source in topo.failed_routers:
        reason = f"Source router {source} is down."
    elif destination in topo.failed_routers:
        reason = f"Destination router {destination} is down."
    else:
        reason = f"No active path exists from {source} to {destination}."
    reason += (f" Recovering the failed links/routers would restore a route (cost {fmt_cost(healthy_cost)})."
               if healthy_cost is not None else " The network is disconnected even without failures.")
    return RouteSummary(algorithm, source, destination, False, [], None, reason, healthy_cost)


def cross_check(topo: Topology, source: str) -> tuple[bool, list[str]]:
    """Do Dijkstra and Bellman-Ford agree on every distance? Returns (agree, differences)."""
    a, b = dijkstra_trace(topo, source)[-1].dist, bellman_ford_trace(topo, source)[-1].dist
    diffs = [f"{r}: Dijkstra={fmt_cost(a[r])}, Bellman-Ford={fmt_cost(b[r])}" for r in sorted(a, key=natural_key)
             if not (a[r] == b[r] == INF or math.isclose(a[r], b[r]))]
    return (not diffs, diffs)


def trace_to_dict(algorithm: str, source: str, steps: list[Step]) -> dict:
    """JSON-friendly export of a trace (∞ becomes null) – handy as 'mock output' for integration tests."""
    def clean(mapping):
        return {k: (None if v == INF else v) for k, v in mapping.items()}
    return {"algorithm": algorithm, "source": source,
            "steps": [{"index": s.index, "title": s.title, "current": s.current, "distances": clean(s.dist),
                       "predecessors": dict(s.prev), "states": dict(s.state), "updated": list(s.updated),
                       "updated_edges": [list(e) for e in s.updated_edges]} for s in steps]}
