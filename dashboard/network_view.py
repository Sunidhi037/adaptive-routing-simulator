"""Interactive network graph (Plotly): routers as nodes, links as weighted edges.

``classify_links`` / ``classify_nodes`` are pure functions (no Plotly needed) so the
colouring rules can be unit-tested; ``build_figure`` imports Plotly lazily.
"""
from __future__ import annotations

from graph_model import Topology, compute_layout, fmt_cost, link_key
from routing_tables import Step

# Draw order = bottom to top, so the selected route always ends up on top.
LINK_ORDER = ("normal", "failed", "tree", "updated", "path")
LINK_STYLE = {  # colour, width, dash, chip fill
    "normal": ("#90a4ae", 2, "solid", "#ffffff"),
    "failed": ("#e53935", 3, "dash", "#ffebee"),
    "tree": ("#42a5f5", 4, "solid", "#e3f2fd"),
    "updated": ("#ffb300", 5, "solid", "#fff8e1"),
    "path": ("#00c853", 7, "solid", "#e8f5e9"),
}
NODE_STYLE = {  # fill, label colour
    "idle": ("#90a4ae", "#ffffff"),
    "unreached": ("#cfd8dc", "#263238"),
    "tentative": ("#90caf9", "#0d1b2a"),
    "final": ("#1565c0", "#ffffff"),
    "current": ("#ff9800", "#1a1a1a"),
    "down": ("#37474f", "#ffffff"),
}
SOURCE_RING, DEST_RING, DEFAULT_RING = "#00c853", "#aa00ff", "#263238"


def classify_links(topo: Topology, step: Step | None = None, path: list[str] | None = None,
                   show_tree: bool = True) -> dict[tuple[str, str], str]:
    """Style name for every link. Priority: failed > path > updated > tree > normal."""
    path_edges = {link_key(a, b) for a, b in zip(path or [], (path or [])[1:])}
    updated = {link_key(u, v) for u, v in step.updated_edges} if step else set()
    tree = {link_key(p, r) for r, p in step.prev.items() if p is not None} if (step and show_tree) else set()
    styles = {}
    for link in topo.links:
        key = link.key
        if not topo.is_link_active(link):
            styles[key] = "failed"
        elif key in path_edges:
            styles[key] = "path"
        elif key in updated:
            styles[key] = "updated"
        elif key in tree:
            styles[key] = "tree"
        else:
            styles[key] = "normal"
    return styles


def classify_nodes(topo: Topology, step: Step | None = None) -> dict[str, str]:
    """Node state: down > current > (final | tentative | unreached) ; 'idle' when no step is shown."""
    out = {}
    for router in topo.routers:
        if router in topo.failed_routers:
            out[router] = "down"
        elif step is None:
            out[router] = "idle"
        elif step.current == router:
            out[router] = "current"
        else:
            out[router] = step.state.get(router, "unreached")
    return out


def _link_hover(link, style) -> str:
    status = {"failed": "FAILED / DOWN", "path": "on selected route", "updated": "updated in this step",
              "tree": "in shortest-path tree"}.get(style, "active")
    return f"<b>{link.key[0]} – {link.key[1]}</b><br>Cost: {fmt_cost(link.cost)}<br>Status: {status}"


def build_figure(topo: Topology, step: Step | None = None, path: list[str] | None = None, path_is_final: bool = False,
                 source: str | None = None, destination: str | None = None, show_tree: bool = True, height: int = 540):
    """Return a Plotly Figure for the topology at the given algorithm step."""
    import plotly.graph_objects as go

    pos = compute_layout(topo)
    link_styles = classify_links(topo, step, path, show_tree)
    node_states = classify_nodes(topo, step)
    legend_names = {"normal": "Active link", "failed": "Failed / down link", "tree": "Shortest-path tree so far",
                    "updated": "Improved in this step", "path": "Selected route" if path_is_final else "Best route so far"}

    fig = go.Figure()
    grouped = {name: [l for l in topo.links if link_styles[l.key] == name] for name in LINK_ORDER}
    for name in LINK_ORDER:
        links = grouped[name]
        if not links:
            continue
        colour, width, dash, _ = LINK_STYLE[name]
        xs, ys = [], []
        for link in links:
            (x0, y0), (x1, y1) = pos[link.a], pos[link.b]
            xs += [x0, x1, None]
            ys += [y0, y1, None]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=colour, width=width, dash=dash),
                                 hoverinfo="skip", name=legend_names[name]))

    # Cost "chips" sit on the middle of each link (a failed link shows a cross before its cost).
    cx, cy, texts, fills, borders, hovers = [], [], [], [], [], []
    for link in topo.links:
        style = link_styles[link.key]
        colour, _, _, chip = LINK_STYLE[style]
        (x0, y0), (x1, y1) = pos[link.a], pos[link.b]
        cx.append((x0 + x1) / 2)
        cy.append((y0 + y1) / 2)
        texts.append(("✖ " if style == "failed" else "") + fmt_cost(link.cost))
        fills.append(chip)
        borders.append(colour)
        hovers.append(_link_hover(link, style))
    fig.add_trace(go.Scatter(x=cx, y=cy, mode="markers+text", text=texts, textfont=dict(color="#111111", size=12),
                             marker=dict(symbol="square", size=30, color=fills, line=dict(color=borders, width=1.5)),
                             hovertext=hovers, hoverinfo="text", showlegend=False))

    # Router nodes.
    nx_, ny_, labels, fill, label_colour, ring, ring_w, hover = [], [], [], [], [], [], [], []
    for router in topo.routers:
        state = node_states[router]
        x, y = pos[router]
        nx_.append(x)
        ny_.append(y)
        labels.append(f"{router}<br>DOWN" if state == "down" else router)
        fill.append(NODE_STYLE[state][0])
        label_colour.append(NODE_STYLE[state][1])
        if router == source:
            ring.append(SOURCE_RING)
            ring_w.append(5)
        elif router == destination:
            ring.append(DEST_RING)
            ring_w.append(5)
        else:
            ring.append(DEFAULT_RING)
            ring_w.append(2)
        lines = [f"<b>{router}</b>"]
        if state == "down":
            lines.append("Router DOWN")
        elif step is not None:
            lines += [f"Distance: {fmt_cost(step.dist[router])}", f"Previous hop: {step.prev[router] or '—'}", f"State: {state}"]
        lines.append("Active neighbours: " + (", ".join(sorted(topo.neighbors(router))) or "none"))
        hover.append("<br>".join(lines))
    fig.add_trace(go.Scatter(x=nx_, y=ny_, mode="markers+text", text=labels, textposition="middle center",
                             textfont=dict(color=label_colour, size=13),
                             marker=dict(size=52, color=fill, line=dict(color=ring, width=ring_w)),
                             hovertext=hover, hoverinfo="text", showlegend=False))

    tags = [(source, "SOURCE", SOURCE_RING)]
    if destination != source:
        tags.append((destination, "DEST", DEST_RING))
    for router, tag, colour in tags:
        if router in pos:
            fig.add_annotation(x=pos[router][0], y=pos[router][1], text=f"<b>{tag}</b>", showarrow=False, yshift=-42,
                               font=dict(color=colour, size=11))

    xs_all, ys_all = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    pad_x = max((max(xs_all) - min(xs_all)) * 0.12, 0.6)
    pad_y = max((max(ys_all) - min(ys_all)) * 0.18, 0.6)
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), showlegend=True,
        legend=dict(orientation="h", yanchor="top", y=-0.02, x=0),
        xaxis=dict(visible=False, range=[min(xs_all) - pad_x, max(xs_all) + pad_x]),
        yaxis=dict(visible=False, range=[min(ys_all) - pad_y, max(ys_all) + pad_y], scaleanchor="x", scaleratio=1),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", hovermode="closest", dragmode="pan",
        uirevision=topo.name,
    )
    return fig
