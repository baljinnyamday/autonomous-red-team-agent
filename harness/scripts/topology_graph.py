#!/usr/bin/env python3
"""Render an engagement's topology as a graph (Mermaid or Graphviz DOT).

Reads the SQLite engagement store written by update_topology and derives the graph
(nodes = hosts, edges = discovered_from / via provenance). Nothing is stored.

    uv run python scripts/topology_graph.py .runs/engagement-<id>.db
    uv run python scripts/topology_graph.py .runs/engagement-<id>.db --format dot -o topology.dot
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_redteam.targets.graph import to_dot, to_mermaid
from agent_redteam.targets.nx_graph import build_digraph
from agent_redteam.targets.state import EngagementState, engagement_id_from_db_path
from agent_redteam.targets.store import EngagementStore

_TEXT_FORMATS = ("mermaid", "dot")
_NX_FORMATS = ("graphml", "png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", type=Path, help="path to .runs/engagement-<id>.db")
    parser.add_argument("--format", choices=(*_TEXT_FORMATS, *_NX_FORMATS), default="mermaid")
    parser.add_argument("--engagement-id", default=None, help="override inferred id")
    parser.add_argument("-o", "--output", type=Path, default=None, help="write to file")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"no such database: {args.db}")

    store = EngagementStore.connect(args.db)
    try:
        engagement_id = engagement_id_from_db_path(args.db, args.engagement_id)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    state = store.load_state(engagement_id)

    if args.format in _NX_FORMATS:
        _write_nx(state, args.format, args.output)
        return

    rendered = to_dot(state) if args.format == "dot" else to_mermaid(state)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


def _write_nx(state: EngagementState, fmt: str, output: Path | None) -> None:
    import networkx as nx

    graph = build_digraph(state)
    if fmt == "graphml":
        target = output or Path(f"topology-{state.engagement_id}.graphml")
        nx.write_graphml(graph, target)
        print(f"wrote {target}")
        return
    # png: needs the optional viz extra (pydot + graphviz binary)
    try:
        from networkx.drawing.nx_pydot import to_pydot
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise SystemExit("png export needs the viz extra: uv sync --extra viz") from exc
    target = output or Path(f"topology-{state.engagement_id}.png")
    to_pydot(graph).write_png(str(target))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
