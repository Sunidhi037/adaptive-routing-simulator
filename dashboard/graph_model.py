"""Topology model, JSON validation and layout for the dashboard.

This module is intentionally self-contained: it does NOT import the
``routing_engine`` package, Streamlit or Plotly, so it can be unit-tested on
its own. It reads the same JSON shape the routing engine uses
(``routers`` + ``links`` + optional ``failed`` flags / ``failed_routers``) and
additionally allows routers to be ``{"id": "R1", "x": 0, "y": 1}`` objects so
the graph can be drawn with a hand-tuned layout.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable


def natural_key(name: str) -> list:
    """Sort key so that R2 < R10 (plain string sort would give R10 < R2)."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def link_key(a: str, b: str) -> tuple[str, str]:
    """Order-independent identifier of an undirected link."""
    first, second = sorted((a, b), key=natural_key)
    return (first, second)


def fmt_cost(value: float | None) -> str:
    """Human-friendly cost: 13, 2.5, or the infinity sign."""
    if value is None or value == math.inf:
        return "∞"
    value = float(value)
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class Link:
    a: str
    b: str
    cost: float
    failed: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return link_key(self.a, self.b)


@dataclass
class Topology:
    name: str
    routers: list[str]
    links: list[Link]
    failed_routers: frozenset[str] = frozenset()
    positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    description: str = ""
    default_source: str | None = None
    default_destination: str | None = None

    # ---- failure handling -------------------------------------------------
    def is_link_active(self, link: Link) -> bool:
        return not link.failed and link.a not in self.failed_routers and link.b not in self.failed_routers

    def neighbors(self, router: str) -> dict[str, float]:
        """Currently usable neighbours and link costs (empty if the router is down)."""
        if router in self.failed_routers:
            return {}
        result: dict[str, float] = {}
        for link in self.links:
            if not self.is_link_active(link):
                continue
            if link.a == router:
                result[link.b] = link.cost
            elif link.b == router:
                result[link.a] = link.cost
        return result

    def failed_link_keys(self) -> set[tuple[str, str]]:
        return {link.key for link in self.links if link.failed}

    def with_failures(self, failed_links: Iterable[tuple[str, str]], failed_routers: Iterable[str]) -> "Topology":
        """Return a copy where exactly the given links/routers are failed (what-if analysis)."""
        failed = {link_key(a, b) for a, b in failed_links}
        links = [replace(link, failed=link.key in failed) for link in self.links]
        return replace(self, links=links, failed_routers=frozenset(failed_routers))

    def healthy(self) -> "Topology":
        """Copy with every failure recovered."""
        return self.with_failures([], [])


# ---- parsing ----------------------------------------------------------------
def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def parse_topology(data: Any, name: str | None = None) -> Topology:
    """Validate a network dictionary and build a Topology. Raises ValueError with a clear message."""
    if not isinstance(data, dict):
        raise ValueError("Network JSON must be an object with 'routers' and 'links'.")
    raw_routers, raw_links = data.get("routers"), data.get("links")
    if not isinstance(raw_routers, list) or not raw_routers:
        raise ValueError("'routers' must be a non-empty list.")
    if not isinstance(raw_links, list):
        raise ValueError("'links' must be a list.")

    routers: list[str] = []
    positions: dict[str, tuple[float, float]] = {}
    for item in raw_routers:
        x = y = None
        if isinstance(item, dict):
            rid, x, y = item.get("id"), item.get("x"), item.get("y")
        else:
            rid = item
        if not isinstance(rid, str) or not rid.strip():
            raise ValueError(f"Invalid router entry: {item!r}")
        rid = rid.strip()
        if rid in routers:
            raise ValueError(f"Duplicate router '{rid}'.")
        routers.append(rid)
        if _is_number(x) and _is_number(y):
            positions[rid] = (float(x), float(y))
    if len(positions) != len(routers):
        positions = {}  # partial coordinates are ignored; an automatic layout is used instead

    links: list[Link] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_links:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid link entry: {item!r}")
        missing = [k for k in ("source", "target", "cost") if k not in item]
        if missing:
            raise ValueError(f"Link {item!r} is missing: {', '.join(missing)}.")
        a, b, cost = str(item["source"]).strip(), str(item["target"]).strip(), item["cost"]
        if a not in routers or b not in routers:
            raise ValueError(f"Link {a} - {b} refers to an unknown router.")
        if a == b:
            raise ValueError(f"Link {a} - {b}: a router cannot link to itself.")
        if not _is_number(cost) or cost < 0:
            raise ValueError(f"Link {a} - {b}: cost must be a non-negative number (got {cost!r}).")
        key = link_key(a, b)
        if key in seen:
            raise ValueError(f"Duplicate link {key[0]} - {key[1]}.")
        seen.add(key)
        links.append(Link(a, b, float(cost), bool(item.get("failed", False))))

    failed_routers = data.get("failed_routers", [])
    if not isinstance(failed_routers, list) or any(r not in routers for r in failed_routers):
        raise ValueError("'failed_routers' must be a list of known router IDs.")

    def _known(value: Any) -> str | None:
        return value if isinstance(value, str) and value in routers else None

    return Topology(
        name=name or str(data.get("name", "Untitled network")),
        routers=routers,
        links=links,
        failed_routers=frozenset(failed_routers),
        positions=positions,
        description=str(data.get("description", "")),
        default_source=_known(data.get("default_source")),
        default_destination=_known(data.get("default_destination")),
    )


def load_scenarios(path: str | Path) -> list[Topology]:
    """Load every scenario of ``sample_data.json`` (or any file with a top-level 'scenarios' list)."""
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    scenarios = payload.get("scenarios") if isinstance(payload, dict) else None
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError(f"{path}: expected a non-empty 'scenarios' list.")
    topologies = []
    for index, scenario in enumerate(scenarios, start=1):
        try:
            topologies.append(parse_topology(scenario))
        except ValueError as exc:
            raise ValueError(f"Scenario #{index}: {exc}") from exc
    return topologies


# ---- layout -----------------------------------------------------------------
def compute_layout(topo: Topology) -> dict[str, tuple[float, float]]:
    """Use supplied coordinates, else a deterministic spring layout, else a circle."""
    if topo.positions and len(topo.positions) == len(topo.routers):
        return dict(topo.positions)
    try:
        import networkx as nx

        graph = nx.Graph()
        graph.add_nodes_from(topo.routers)
        graph.add_edges_from((link.a, link.b) for link in topo.links)
        pos = nx.spring_layout(graph, seed=7)
        return {r: (float(pos[r][0]), float(pos[r][1])) for r in topo.routers}
    except Exception:  # networkx missing or layout failure -> always have a fallback
        count = len(topo.routers)
        return {
            r: (math.cos(2 * math.pi * i / count - math.pi / 2), math.sin(2 * math.pi * i / count - math.pi / 2))
            for i, r in enumerate(topo.routers)
        }


# ---- link status table --------------------------------------------------------
def link_status_rows(topo: Topology) -> list[dict[str, str]]:
    rows = []
    for link in sorted(topo.links, key=lambda l: [natural_key(l.key[0]), natural_key(l.key[1])]):
        if link.failed:
            status, reason = "🔴 Failed", "Link marked as failed"
        elif link.a in topo.failed_routers or link.b in topo.failed_routers:
            down = ", ".join(r for r in (link.a, link.b) if r in topo.failed_routers)
            status, reason = "🟠 Down", f"Router {down} is down"
        else:
            status, reason = "🟢 Active", ""
        rows.append({"Link": f"{link.key[0]} – {link.key[1]}", "Cost": fmt_cost(link.cost), "Status": status, "Reason": reason})
    return rows
