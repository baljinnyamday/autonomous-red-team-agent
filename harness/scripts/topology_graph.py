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
from agent_redteam.targets.store import EngagementStore


def _engagement_id(db_path: Path, override: str | None) -> str:
    if override:
        return override
    stem = db_path.stem
    if stem.startswith("engagement-"):
        return stem.removeprefix("engagement-")
    raise SystemExit(f"cannot infer engagement id from {db_path.name!r}; pass --engagement-id")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", type=Path, help="path to .runs/engagement-<id>.db")
    parser.add_argument("--format", choices=("mermaid", "dot"), default="mermaid")
    parser.add_argument("--engagement-id", default=None, help="override inferred id")
    parser.add_argument("-o", "--output", type=Path, default=None, help="write to file")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"no such database: {args.db}")

    store = EngagementStore.connect(args.db)
    state = store.load_state(_engagement_id(args.db, args.engagement_id))
    rendered = to_dot(state) if args.format == "dot" else to_mermaid(state)

    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
