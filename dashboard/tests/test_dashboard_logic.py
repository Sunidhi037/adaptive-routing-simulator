"""Tests for the dashboard's pure-Python logic (no Streamlit / Plotly needed).

Run from the project root:
    python -m unittest discover -s dashboard/tests -v
(``python -m pytest dashboard/tests`` also works if pytest is installed.)
"""
import itertools
import json
import math
import sys
import unittest
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parents[1]
ROOT = DASHBOARD_DIR.parent
sys.path.insert(0, str(DASHBOARD_DIR))

from graph_model import (compute_layout, link_key, link_status_rows, load_scenarios, natural_key,  # noqa: E402
                         parse_topology)
from network_view import classify_links, classify_nodes  # noqa: E402
from routing_tables import (BELLMAN_FORD, DIJKSTRA, INF, bellman_ford_trace, cross_check, dijkstra_trace,  # noqa: E402
                            distance_rows, path_to, routing_rows, run_algorithm, summarize_route, trace_to_dict)

SCENARIOS = {t.name.split(".")[0]: t for t in load_scenarios(DASHBOARD_DIR / "sample_data.json")}
HEALTHY, LINK_FAIL, ROUTER_FAIL, PARTITION, RING = (SCENARIOS[str(i)] for i in range(1, 6))


def floyd_warshall(topo):
    """Independent reference implementation used to validate both traces."""
    d = {a: {b: (0 if a == b else INF) for b in topo.routers} for a in topo.routers}
    for a in topo.routers:
        for b, w in topo.neighbors(a).items():
            d[a][b] = min(d[a][b], w)
    for k, i, j in itertools.product(topo.routers, repeat=3):
        d[i][j] = min(d[i][j], d[i][k] + d[k][j])
    return d


class ParsingTests(unittest.TestCase):
    def test_all_sample_scenarios_load(self):
        self.assertEqual(len(SCENARIOS), 5)
        for topo in SCENARIOS.values():
            self.assertEqual(len(compute_layout(topo)), len(topo.routers))

    def test_engine_style_json_without_positions_loads(self):
        data = json.loads((ROOT / "data" / "sample_network.json").read_text()) if (ROOT / "data" / "sample_network.json").exists() else \
            {"routers": ["A", "B"], "links": [{"source": "A", "target": "B", "cost": 1}]}
        topo = parse_topology(data)
        self.assertEqual(len(compute_layout(topo)), len(topo.routers))  # automatic layout kicks in

    def test_invalid_inputs_raise_value_error(self):
        bad_inputs = [
            [], {"routers": [], "links": []}, {"routers": ["A", "A"], "links": []},
            {"routers": ["A", "B"], "links": [{"source": "A", "target": "Z", "cost": 1}]},
            {"routers": ["A", "B"], "links": [{"source": "A", "target": "A", "cost": 1}]},
            {"routers": ["A", "B"], "links": [{"source": "A", "target": "B", "cost": -2}]},
            {"routers": ["A", "B"], "links": [{"source": "A", "target": "B", "cost": "x"}]},
            {"routers": ["A", "B"], "links": [{"source": "A", "target": "B"}]},
            {"routers": ["A", "B"], "links": [{"source": "A", "target": "B", "cost": 1}, {"source": "B", "target": "A", "cost": 2}]},
            {"routers": ["A", "B"], "links": [], "failed_routers": ["Q"]},
        ]
        for data in bad_inputs:
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_topology(data)

    def test_natural_sort_and_link_key(self):
        self.assertEqual(sorted(["R10", "R2", "R1"], key=natural_key), ["R1", "R2", "R10"])
        self.assertEqual(link_key("R5", "R2"), link_key("R2", "R5"))

    def test_with_failures_is_non_destructive(self):
        failed = HEALTHY.with_failures([("R6", "R5")], ["R2"])
        self.assertEqual(failed.failed_link_keys(), {("R5", "R6")})
        self.assertEqual(failed.failed_routers, frozenset({"R2"}))
        self.assertEqual(HEALTHY.failed_link_keys(), set())  # original untouched
        self.assertNotIn("R2", failed.neighbors("R1"))


class AlgorithmTests(unittest.TestCase):
    def test_known_route_matches_engine_readme(self):
        for algorithm in (DIJKSTRA, BELLMAN_FORD):
            result = summarize_route(algorithm, HEALTHY, "R1", "R8")
            self.assertTrue(result.reachable)
            self.assertEqual(result.path, ["R1", "R3", "R5", "R6", "R7", "R8"])
            self.assertEqual(result.total_cost, 13)

    def test_link_failure_detour_costs_more(self):
        for algorithm in (DIJKSTRA, BELLMAN_FORD):
            result = summarize_route(algorithm, LINK_FAIL, "R1", "R8")
            self.assertEqual(result.total_cost, 15)
            self.assertEqual(result.healthy_cost, 13)
            self.assertNotIn(("R5", "R6"), zip(result.path, result.path[1:]))

    def test_router_failure_avoids_failed_router(self):
        result = summarize_route(DIJKSTRA, ROUTER_FAIL, "R1", "R8")
        self.assertEqual(result.total_cost, 15)
        self.assertNotIn("R6", result.path)

    def test_unreachable_status_and_message(self):
        for algorithm in (DIJKSTRA, BELLMAN_FORD):
            result = summarize_route(algorithm, PARTITION, "R1", "R6")
            self.assertFalse(result.reachable)
            self.assertIsNone(result.total_cost)
            self.assertEqual(result.to_dict(), {"source": "R1", "destination": "R6", "status": "unreachable",
                                                "reachable": False, "path": [], "total_cost": None})
            self.assertIn("Recovering", result.message)  # reachable again once the link is restored
        recovered = PARTITION.with_failures([], [])
        self.assertEqual(summarize_route(DIJKSTRA, recovered, "R1", "R6").total_cost, 9)

    def test_source_or_destination_down(self):
        down_src = HEALTHY.with_failures([], ["R1"])
        for algorithm in (DIJKSTRA, BELLMAN_FORD):
            steps = run_algorithm(algorithm, down_src, "R1")
            self.assertEqual(len(steps), 1)
            self.assertFalse(summarize_route(algorithm, down_src, "R1", "R8", steps).reachable)
        down_dst = HEALTHY.with_failures([], ["R8"])
        result = summarize_route(DIJKSTRA, down_dst, "R1", "R8")
        self.assertFalse(result.reachable)
        self.assertIn("Destination router R8 is down", result.message)

    def test_same_source_and_destination(self):
        result = summarize_route(DIJKSTRA, HEALTHY, "R3", "R3")
        self.assertTrue(result.reachable)
        self.assertEqual((result.path, result.total_cost), (["R3"], 0))

    def test_both_algorithms_match_floyd_warshall_for_every_pair(self):
        for name, topo in SCENARIOS.items():
            reference = floyd_warshall(topo)
            for source in topo.routers:
                for trace in (dijkstra_trace, bellman_ford_trace):
                    final = trace(topo, source)[-1]
                    for dest in topo.routers:
                        expected = reference[source][dest] if source not in topo.failed_routers else INF
                        if dest in topo.failed_routers:
                            expected = INF
                        with self.subTest(scenario=name, trace=trace.__name__, src=source, dst=dest):
                            if expected == INF:
                                self.assertEqual(final.dist[dest], INF)
                            else:
                                self.assertTrue(math.isclose(final.dist[dest], expected))
                self.assertTrue(cross_check(topo, source)[0])

    def test_reconstructed_path_cost_equals_distance(self):
        for topo in SCENARIOS.values():
            costs = {link.key: link.cost for link in topo.links}
            for algorithm in (DIJKSTRA, BELLMAN_FORD):
                for source in topo.routers:
                    final = run_algorithm(algorithm, topo, source)[-1]
                    for dest in topo.routers:
                        if final.dist[dest] < INF:
                            path = path_to(final.prev, source, dest)
                            self.assertAlmostEqual(sum(costs[link_key(a, b)] for a, b in zip(path, path[1:])), final.dist[dest])

    def test_optional_cross_check_against_routing_engine(self):
        sys.path.insert(0, str(ROOT))
        try:
            from routing_engine import find_route, network_from_dict
        except ImportError:
            self.skipTest("routing_engine not importable from here")
        finally:
            sys.path.remove(str(ROOT))
        for topo in SCENARIOS.values():
            engine_net = network_from_dict({"routers": topo.routers, "failed_routers": sorted(topo.failed_routers),
                                            "links": [{"source": l.a, "target": l.b, "cost": l.cost, "failed": l.failed} for l in topo.links]})
            for src, dst in itertools.permutations(topo.routers, 2):
                engine = find_route(engine_net, src, dst)
                mine = summarize_route(DIJKSTRA, topo, src, dst)
                with self.subTest(scenario=topo.name, src=src, dst=dst):
                    self.assertEqual(engine.reachable, mine.reachable)
                    if engine.reachable:
                        self.assertAlmostEqual(engine.total_cost, mine.total_cost)


class StepTraceTests(unittest.TestCase):
    def test_dijkstra_distances_never_increase_and_finalised_never_change(self):
        steps = dijkstra_trace(HEALTHY, "R1")
        for before, after in zip(steps, steps[1:]):
            for router in HEALTHY.routers:
                self.assertLessEqual(after.dist[router], before.dist[router])
                if before.state[router] == "final":
                    self.assertEqual(after.dist[router], before.dist[router])
        self.assertTrue(steps[-1].is_last)
        self.assertEqual([s.index for s in steps], list(range(len(steps))))

    def test_dijkstra_finalises_in_distance_order(self):
        order = [s.current for s in dijkstra_trace(HEALTHY, "R1") if s.current]
        final = dijkstra_trace(HEALTHY, "R1")[-1].dist
        self.assertEqual([final[r] for r in order], sorted(final[r] for r in order))

    def test_bellman_ford_takes_multiple_iterations_on_ring_demo(self):
        steps = bellman_ford_trace(RING, "R1")
        iterations = [s for s in steps if s.title.startswith("Iteration")]
        self.assertGreaterEqual(len(iterations), 4)
        self.assertLessEqual(len(iterations), len(RING.routers) - 1)
        self.assertEqual(steps[-1].dist["R2"], 10)

    def test_routing_table_changes_are_flagged(self):
        steps = dijkstra_trace(HEALTHY, "R1")
        rows = {r["Destination"]: r for r in routing_rows(steps[2], steps[1])}  # R3 finalised
        self.assertEqual(rows["R2"]["Change"], "🔄 updated")  # 10 -> 7 via R3
        self.assertEqual(rows["R5"]["Change"], "🆕 new route")
        self.assertEqual(rows["R5"]["Next hop"], "R3")
        self.assertEqual(rows["R8"]["Status"], "No route yet")
        self.assertEqual(routing_rows(steps[0])[0]["Change"], "")  # nothing to compare with at step 0

    def test_final_tables_mark_unreachable(self):
        final = dijkstra_trace(PARTITION, "R1")[-1]
        rows = {r["Destination"]: r for r in routing_rows(final)}
        self.assertEqual(rows["R6"]["Status"], "Unreachable")
        self.assertEqual((rows["R6"]["Cost"], rows["R6"]["Next hop"]), ("∞", "—"))
        self.assertEqual({r["Router"]: r["State"] for r in distance_rows(final)}["R5"], "Unreachable")

    def test_trace_export_is_json_serialisable(self):
        text = json.dumps(trace_to_dict(DIJKSTRA, "R1", dijkstra_trace(PARTITION, "R1")))
        self.assertIn("null", text)  # infinity exported as null


class ViewClassificationTests(unittest.TestCase):
    def test_failed_links_and_routers(self):
        styles = classify_links(LINK_FAIL, path=["R1", "R3", "R5", "R7", "R8"])
        self.assertEqual(styles[("R5", "R6")], "failed")
        self.assertEqual(styles[("R3", "R5")], "path")
        down = classify_links(ROUTER_FAIL)  # links touching a down router count as failed too
        self.assertEqual(down[("R4", "R6")], "failed")
        self.assertEqual(classify_nodes(ROUTER_FAIL)["R6"], "down")

    def test_step_styles(self):
        steps = dijkstra_trace(HEALTHY, "R1")
        styles = classify_links(HEALTHY, steps[2])
        self.assertEqual(styles[("R3", "R5")], "updated")
        self.assertEqual(styles[("R1", "R3")], "tree")
        self.assertEqual(styles[("R6", "R8")], "normal")
        self.assertEqual(classify_nodes(HEALTHY, steps[2])["R3"], "current")
        self.assertEqual(classify_nodes(HEALTHY, steps[2])["R8"], "unreached")
        self.assertEqual(classify_links(HEALTHY, steps[2], show_tree=False)[("R1", "R3")], "normal")

    def test_link_status_rows(self):
        rows = {r["Link"]: r for r in link_status_rows(ROUTER_FAIL)}
        self.assertIn("Down", rows["R4 – R6"]["Status"])
        self.assertIn("Active", rows["R1 – R2"]["Status"])
        self.assertIn("Failed", {r["Link"]: r for r in link_status_rows(LINK_FAIL)}["R5 – R6"]["Status"])


if __name__ == "__main__":
    unittest.main()
