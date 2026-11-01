"""Adaptive Routing Algorithm Visualizer - Streamlit dashboard (Member 3 module).

Run from the project root:   streamlit run dashboard/app.py

The dashboard only reads JSON (``sample_data.json`` or an uploaded file); it does
not import the routing engine, so it works independently of the other modules.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from graph_model import Topology, fmt_cost, link_status_rows, load_scenarios, natural_key, parse_topology
from network_view import build_figure
from routing_tables import (ALGORITHMS, cross_check, distance_rows, path_to, routing_rows, run_algorithm,
                            summarize_route, trace_to_dict)

st.set_page_config(page_title="Adaptive Routing Visualizer", page_icon="🛰️", layout="wide")

DATA_FILE = Path(__file__).with_name("sample_data.json")


# ---- small helpers --------------------------------------------------------------
def _plot(fig) -> None:
    """Full-width Plotly chart that works on both old and new Streamlit versions."""
    config = {"displaylogo": False, "scrollZoom": True}
    try:
        has_width = "width" in inspect.signature(st.plotly_chart).parameters
    except (TypeError, ValueError):
        has_width = False
    if has_width:
        st.plotly_chart(fig, width="stretch", config=config)
    else:
        st.plotly_chart(fig, use_container_width=True, config=config)


def _scenario_id(topo: Topology) -> str:
    raw = repr((topo.name, topo.routers, [(l.a, l.b, l.cost, l.failed) for l in topo.links], sorted(topo.failed_routers)))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _move(delta: int = 0, to: int | None = None, last: int = 0) -> None:
    """Button callback: change the shared step counter (also drives the slider)."""
    current = st.session_state.get("step", 0)
    st.session_state["step"] = max(0, min(last, to if to is not None else current + delta))


def _reset_failures() -> None:
    """Changing the widget keys makes both failure selectors start again from the scenario defaults."""
    st.session_state["_reset_count"] = st.session_state.get("_reset_count", 0) + 1


# ---- load data ---------------------------------------------------------------------
try:
    scenarios = load_scenarios(DATA_FILE)
except (OSError, ValueError) as exc:
    st.error(f"Could not load {DATA_FILE.name}: {exc}")
    st.stop()

# ---- sidebar controls ------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Controls")
    scenario_name = st.selectbox("Network scenario", [t.name for t in scenarios])
    base = next(t for t in scenarios if t.name == scenario_name)
    uploaded = st.file_uploader("…or upload a network JSON", type=["json"],
                                help="Same shape as data/sample_network.json. Routers may also be {id, x, y} objects.")
    if uploaded is not None:
        try:
            base = parse_topology(json.loads(uploaded.getvalue().decode("utf-8")), name=f"Uploaded: {uploaded.name}")
            st.success(f"Using uploaded network ({len(base.routers)} routers, {len(base.links)} links).")
        except (ValueError, UnicodeDecodeError) as exc:
            st.error(f"Invalid network JSON – using the selected scenario instead.\n\n{exc}")
    if base.description:
        st.caption(base.description)

    sid = _scenario_id(base)
    routers = sorted(base.routers, key=natural_key)
    default_src = base.default_source or routers[0]
    default_dst = base.default_destination or routers[-1]
    source = st.selectbox("Source router", routers, index=routers.index(default_src), key=f"src-{sid}")
    destination = st.selectbox("Destination router", routers, index=routers.index(default_dst), key=f"dst-{sid}")
    algorithm = st.radio("Algorithm", ALGORITHMS, horizontal=True)

    st.subheader("Failures (what-if)")
    cost_of = {l.key: l.cost for l in base.links}
    link_keys = sorted(cost_of, key=lambda k: [natural_key(k[0]), natural_key(k[1])])
    resets = st.session_state.get("_reset_count", 0)
    links_key, routers_key = f"failed-links-{sid}-{resets}", f"failed-routers-{sid}-{resets}"
    failed_links = st.multiselect("Failed links", link_keys, default=sorted(base.failed_link_keys()), key=links_key,
                                  format_func=lambda k: f"{k[0]} – {k[1]}  (cost {fmt_cost(cost_of[k])})")
    failed_routers = st.multiselect("Failed routers", routers, default=sorted(base.failed_routers, key=natural_key), key=routers_key)
    st.button("↺ Reset failures to scenario defaults", on_click=_reset_failures)

    st.subheader("Display")
    show_route = st.checkbox("Highlight route to destination", value=True)
    show_tree = st.checkbox("Show shortest-path tree", value=True)

topo = base.with_failures(failed_links, failed_routers)

# ---- run algorithm -------------------------------------------------------------------------
steps = run_algorithm(algorithm, topo, source)
summary = summarize_route(algorithm, topo, source, destination, steps)
n_steps = len(steps)

signature = (sid, algorithm, source, tuple(sorted(failed_links)), tuple(sorted(failed_routers)))
if st.session_state.get("_signature") != signature:  # new scenario / algorithm / failures -> restart from step 0
    st.session_state["_signature"] = signature
    st.session_state["step"] = 0
st.session_state["step"] = max(0, min(st.session_state.get("step", 0), n_steps - 1))
idx = st.session_state["step"]

# ---- header + final result ---------------------------------------------------------------------
st.title("🛰️ Adaptive Routing Algorithm Visualizer")
st.caption(f"Computer Networks PBL · {algorithm} · {topo.name}")

if summary.reachable:
    st.success(f"✅ **Route {source} → {destination}:** {' → '.join(summary.path)}   |   **Total cost: {fmt_cost(summary.total_cost)}**")
else:
    st.error(f"⛔ **UNREACHABLE – {source} → {destination}.** {summary.message}")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Status", "Reachable" if summary.reachable else "Unreachable")
delta = None
if summary.reachable and summary.healthy_cost is not None and summary.total_cost > summary.healthy_cost:
    delta = f"+{fmt_cost(summary.total_cost - summary.healthy_cost)} vs healthy network"
m2.metric("Route cost", fmt_cost(summary.total_cost) if summary.reachable else "∞", delta=delta, delta_color="inverse")
m3.metric("Hops", max(len(summary.path) - 1, 0) if summary.reachable else "—")
m4.metric("Failed links / routers", f"{sum(1 for l in topo.links if l.failed)} / {len(topo.failed_routers)}")
if source == destination:
    st.info("Source and destination are the same router, so the route cost is 0.")

# ---- step controls -------------------------------------------------------------------------------
st.markdown("### Step-by-step progress")
c_first, c_prev, c_slider, c_next, c_last = st.columns([1, 1, 6, 1, 1])
c_first.button("⏮ First", on_click=_move, kwargs=dict(to=0, last=n_steps - 1), disabled=idx == 0)
c_prev.button("◀ Prev", on_click=_move, kwargs=dict(delta=-1, last=n_steps - 1), disabled=idx == 0)
c_next.button("Next ▶", on_click=_move, kwargs=dict(delta=1, last=n_steps - 1), disabled=idx >= n_steps - 1)
c_last.button("Last ⏭", on_click=_move, kwargs=dict(to=n_steps - 1, last=n_steps - 1), disabled=idx >= n_steps - 1)
if n_steps > 1:
    c_slider.slider("Step", 0, n_steps - 1, key="step", label_visibility="collapsed")
else:
    c_slider.caption("This scenario has a single step.")

step = steps[idx]
previous = steps[idx - 1] if idx > 0 else None

# ---- graph + explanation ----------------------------------------------------------------------------
col_graph, col_text = st.columns([3, 2])
with col_graph:
    path = path_to(step.prev, source, destination) if (show_route and step.dist[destination] < math.inf) else None
    path_is_final = step.is_last or step.state.get(destination) == "final"
    _plot(build_figure(topo, step=step, path=path, path_is_final=path_is_final, source=source,
                       destination=destination, show_tree=show_tree))
with col_text:
    st.subheader(f"Step {idx + 1} of {n_steps}: {step.title}")
    st.progress(idx / (n_steps - 1) if n_steps > 1 else 1.0)
    st.markdown(step.explanation)
    with st.expander("Legend"):
        st.markdown(
            "**Routers** – 🟦 final · 🔹 tentative · ⬜ not reached · 🟧 finalised in this step · ⬛ router down  \n"
            "**Rings** – green = source, purple = destination  \n"
            "**Links** – grey = active · red dashed ✖ = failed/down · blue = shortest-path tree · "
            "amber = improved this step · green = route to destination  \n"
            "The number on each link is its cost. Hover over routers/links for details; scroll to zoom, drag to pan."
        )

# ---- tables --------------------------------------------------------------------------------------------
col_dist, col_route = st.columns(2)
with col_dist:
    st.markdown(f"#### Distance table (from {source}) · step {idx + 1}")
    st.dataframe(pd.DataFrame(distance_rows(step)), hide_index=True)
with col_route:
    st.markdown(f"#### Routing table of {source} · step {idx + 1}")
    st.dataframe(pd.DataFrame(routing_rows(step, previous)), hide_index=True)
    st.caption("“Change” compares this step with the previous one.")

# ---- extras ------------------------------------------------------------------------------------------------
with st.expander("🔗 Link costs and failure status", expanded=bool(failed_links or failed_routers)):
    st.dataframe(pd.DataFrame(link_status_rows(topo)), hide_index=True)

with st.expander("🧪 Cross-check: Dijkstra vs Bellman-Ford"):
    agree, diffs = cross_check(topo, source)
    if agree:
        st.success("Both algorithms give identical distances to every router from this source.")
    else:
        st.warning("The algorithms disagree:\n\n" + "\n".join(f"- {d}" for d in diffs))

with st.expander("📦 Route result as JSON (same shape as routing_engine's RouteResult.to_dict())"):
    st.json(summary.to_dict())
    st.download_button("⬇ Download full step trace (JSON)", data=json.dumps(trace_to_dict(algorithm, source, steps), indent=2),
                       file_name=f"trace_{algorithm.lower()}_{source}.json", mime="application/json")
