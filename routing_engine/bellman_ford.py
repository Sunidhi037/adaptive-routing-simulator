"""Bellman-Ford shortest paths and per-router routing table generation."""
from math import inf

def bellman_ford(network, source: str, destination: str | None = None) -> dict:
    if source not in network.routers() or (destination is not None and destination not in network.routers()):
        return {"source": source, "destination": destination, "status": "unknown_router",
                "reachable": False, "path": [], "total_cost": None, "steps": []}
    if source in network.failed_routers:
        return {"source": source, "destination": destination, "status": "unreachable",
                "reachable": False, "path": [], "total_cost": None, "steps": []}

    dist = {r: inf for r in network.routers()}
    prev = {r: None for r in network.routers()}
    dist[source] = 0
    edges = []
    for u in network.routers():
        for v, weight in network.neighbors(u).items():
            edges.append((u, v, weight))

    steps = []
    for iteration in range(1, len(network.routers())):
        updates = []
        changed = False
        for u, v, weight in edges:
            if dist[u] != inf and dist[u] + weight < dist[v]:
                old = dist[v]
                dist[v] = dist[u] + weight
                prev[v] = u
                updates.append({"from": u, "to": v, "old_cost": old if old != inf else None,
                                "new_cost": dist[v], "link_cost": weight})
                changed = True
        steps.append({"iteration": iteration,
                      "distances": {k: (x if x != inf else None) for k, x in dist.items()},
                      "updates": updates})
        if not changed:
            break

    # Negative cycle detection is included for completeness; current Network rejects negative edges.
    for u, v, weight in edges:
        if dist[u] != inf and dist[u] + weight < dist[v]:
            return {"source": source, "destination": destination, "status": "negative_cycle",
                    "reachable": False, "path": [], "total_cost": None, "steps": steps}

    def path_to(target):
        if dist[target] == inf:
            return []
        path, seen, current = [], set(), target
        while current is not None:
            if current in seen:
                return []
            seen.add(current)
            path.append(current)
            current = prev[current]
        return list(reversed(path))

    path = path_to(destination) if destination else []
    cost = dist[destination] if destination and dist[destination] != inf else (0 if destination == source else None)
    return {"source": source, "destination": destination, "status": "ok" if destination is None or path else "unreachable",
            "reachable": destination is None or bool(path), "path": path, "total_cost": cost,
            "distances": {k: (v if v != inf else None) for k, v in dist.items()},
            "predecessors": prev, "steps": steps}

def build_routing_table(network, source: str) -> dict:
    result = bellman_ford(network, source)
    table = {}
    for destination in network.routers():
        if destination == source:
            table[destination] = {"destination": destination, "next_hop": source,
                                  "path": [source], "total_cost": 0, "reachable": True, "status": "ok"}
            continue
        cost = result["distances"].get(destination)
        path = []
        if cost is not None:
            current, seen = destination, set()
            while current is not None and current not in seen:
                seen.add(current)
                path.append(current)
                current = result["predecessors"].get(current)
            path.reverse()
            if not path or path[0] != source:
                path = []
        reachable = bool(path)
        table[destination] = {"destination": destination,
                              "next_hop": path[1] if reachable and len(path) > 1 else None,
                              "path": path, "total_cost": cost if reachable else None,
                              "reachable": reachable, "status": "ok" if reachable else "unreachable"}
    return table
