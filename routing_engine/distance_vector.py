"""Synchronous distance-vector update/convergence demonstration."""
from math import inf

def simulate_distance_vector(network, max_rounds: int | None = None) -> dict:
    routers = list(network.routers())
    max_rounds = max_rounds or max(1, len(routers) * 2)
    vectors = {r: {d: (0 if r == d else inf) for d in routers} for r in routers}
    next_hops = {r: {d: (r if r == d else None) for d in routers} for r in routers}
    rounds = []

    for round_no in range(1, max_rounds + 1):
        updated = {r: dict(vectors[r]) for r in routers}
        updated_hops = {r: dict(next_hops[r]) for r in routers}
        changes = []
        for router in routers:
            if router in network.failed_routers:
                continue
            for neighbor, link_cost in network.neighbors(router).items():
                for destination in routers:
                    neighbor_cost = vectors[neighbor][destination]
                    if neighbor_cost == inf:
                        continue
                    candidate = link_cost + neighbor_cost
                    if candidate < updated[router][destination]:
                        old = updated[router][destination]
                        updated[router][destination] = candidate
                        updated_hops[router][destination] = neighbor
                        changes.append({"router": router, "destination": destination,
                                        "via": neighbor, "old_cost": old if old != inf else None,
                                        "new_cost": candidate})
        vectors, next_hops = updated, updated_hops
        rounds.append({"round": round_no, "changes": changes,
                       "distance_vectors": {r: {d: (c if c != inf else None) for d, c in row.items()}
                                            for r, row in vectors.items()}})
        if not changes:
            return {"converged": True, "rounds": rounds, "distance_vectors": rounds[-1]["distance_vectors"],
                    "routing_tables": _tables(routers, vectors, next_hops)}
    return {"converged": False, "rounds": rounds,
            "distance_vectors": {r: {d: (c if c != inf else None) for d, c in row.items()} for r, row in vectors.items()},
            "routing_tables": _tables(routers, vectors, next_hops)}

def _tables(routers, vectors, next_hops):
    tables = {}
    for router in routers:
        tables[router] = {}
        for destination in routers:
            cost = vectors[router][destination]
            hop = next_hops[router][destination]
            tables[router][destination] = {
                "destination": destination, "next_hop": hop,
                "total_cost": cost if cost != inf else None,
                "reachable": cost != inf,
                "status": "ok" if cost != inf else "unreachable"
            }
    return tables
