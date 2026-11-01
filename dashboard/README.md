# Routing Visualizer Dashboard (Member 3 module)

Interactive **Streamlit + Plotly** dashboard for the *Adaptive Routing Algorithm Visualizer Using Dijkstra and
Bellman-Ford* Computer Networks PBL project.

The dashboard is **independent of the other modules**: it does not import `routing_engine`, it only reads JSON
(`sample_data.json` or an uploaded file) and computes its own step-by-step *visualisation trace*. Nothing outside the
`dashboard/` folder is modified.

## Setup

Python 3.10+ is recommended. From the **project root**:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux:        source .venv/bin/activate
python -m pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

The app opens at <http://localhost:8501>.

## Demo script (≈ 3 minutes)

1. Pick **"1. Sample network"**, source `R1`, destination `R8`, algorithm **Dijkstra**. The banner shows the route
   `R1 → R3 → R5 → R6 → R7 → R8` with total cost **13**.
2. Press **Next ▶** (or drag the slider). Each step highlights the router being finalised (orange), the links that were
   improved (amber) and the shortest-path tree (blue). The **distance table** and the **routing table of R1** update and
   the *Change* column shows which routing entries changed.
3. Switch the algorithm to **Bellman-Ford**: steps are now *iterations* over all links. Final cost is the same
   (open *Cross-check* to confirm both algorithms agree).
4. Choose **"2. Link failure demo"** (or tick `R5 – R6` under *Failed links*): the link turns red/dashed with ✖, the route
   detours and the cost becomes **15** (`+2 vs healthy network`).
5. Choose **"4. Unreachable demo"** → red **UNREACHABLE** banner, routing-table rows say *Unreachable* (`∞`). The message tells
   you that recovering the failed link would restore a route (cost 9).
6. Choose **"5. Bellman-Ford multi-round demo"** with Bellman-Ford to see several iterations before convergence.

## Features ↔ task checklist

| # | Requirement | Where |
|---|-------------|-------|
| 1 | Interactive network graph | Plotly graph (hover, zoom, pan) – `network_view.py` |
| 2 | Routers = nodes, links = weighted edges | Cost chip on every link |
| 3 | Select source & destination | Sidebar |
| 4 | Dijkstra / Bellman-Ford selector | Sidebar radio |
| 5 | Step-by-step button / slider | First / Prev / Next / Last buttons + slider |
| 6 | Distance table + routing table at every step | Two tables under the graph – `routing_tables.py` |
| 7 | Highlight selected route | Green path (dashed legend entry “Best route so far” until final) |
| 8 | Link cost + failed-link status | Cost chips, red dashed ✖ links, dark `DOWN` routers, *Link costs and failure status* table, what-if failure selectors |
| 9 | Route cost + unreachable status | Green / red banner + metrics (status, cost, hops, delta vs healthy) |
| 10 | Test with sample JSON | `sample_data.json` (5 scenarios) + `tests/` |

## Files

```
dashboard/
├── app.py               Streamlit UI (sidebar, step controls, banners, tables)
├── network_view.py      Plotly figure + colouring rules (classify_links / classify_nodes)
├── routing_tables.py    Dijkstra & Bellman-Ford step traces, distance/routing tables, route summary
├── graph_model.py       Topology model, JSON validation, layout, link-status table
├── sample_data.json     5 demo scenarios (healthy, link failure, router failure, partition, ring)
├── requirements.txt     Dashboard-only dependencies (root requirements.txt is untouched)
├── tests/test_dashboard_logic.py
└── screenshots/         Put demo screenshots here
```

## Input JSON format

Same shape as `data/sample_network.json`, so that file can be uploaded directly in the sidebar. Routers may optionally be
objects with coordinates; without coordinates an automatic layout is used.

```json
{
  "name": "My network",
  "routers": [{"id": "R1", "x": 0, "y": 1}, "R2"],
  "links": [{"source": "R1", "target": "R2", "cost": 4, "failed": false}],
  "failed_routers": []
}
```

Validation (clear error message in the sidebar): non-empty unique router IDs, links between known routers, no self-links,
no duplicate links, costs must be finite and **non-negative** (links are undirected, so a negative cost would be a
negative cycle; this also matches the routing engine's contract).

`sample_data.json` wraps several of these objects in a top-level `"scenarios"` list and adds `description`,
`default_source` and `default_destination`.

## How the steps work

* **Dijkstra** – step 0 initialises distances; every following step finalises the unvisited router with the smallest
  distance and relaxes its links; the last step summarises unreachable routers.
* **Bellman-Ford** – step 0 initialises; each step is one full pass (iteration) over all active links in both
  directions; it stops early when nothing changes. The last step reports the negative-cycle check.
* **Routing table** – derived from the predecessor pointers at the displayed step: `next hop` is the first router on the
  path from the source. Entries are *Tentative* until finalised, *No route yet* / *Unreachable* when the distance is ∞.
* Failed links/routers are excluded from the computation but stay visible (red dashed link / dark `DOWN` router).

## Integration notes

* The route summary (*Route result as JSON*) uses the same keys as `RouteResult.to_dict()` in `routing_engine`
  (`source, destination, status, reachable, path, total_cost`), so real engine output can be dropped in later.
* *Download full step trace (JSON)* exports every step (`distances`, `predecessors`, `updated`, …) – usable as a mock
  output for the simulation module.
* Costs are simulated link-cost units, not measured latency.

## Tests

```bash
python -m unittest discover -s dashboard/tests -v
```

The tests check both algorithms against an independent Floyd–Warshall implementation for every router pair of every sample
scenario, failure / unreachable behaviour, JSON validation, table change-detection and the colouring rules. One optional
test additionally compares results with `routing_engine.find_route` when the engine is importable (it is only a test;
the dashboard itself never imports it). The root `pytest` configuration (`testpaths = ["tests"]`) is not affected.

## Screenshots

Add PNGs to `dashboard/screenshots/` (see the handoff checklist): `01-healthy-final.png`, `02-dijkstra-step.png`,
`03-bellman-ford-iteration.png`, `04-link-failure.png`, `05-unreachable.png`, `06-link-status-table.png`.
