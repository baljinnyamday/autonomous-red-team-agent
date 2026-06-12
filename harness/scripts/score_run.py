#!/usr/bin/env python3
"""Score a finished engagement from its SQLite topology.

uv run python scripts/score_run.py .runs/engagement-<id>.db --goal db-10-0-0-9
uv run python scripts/score_run.py .runs/engagement-<id>.db --goal db-10-0-0-9 --optimal-hops 2
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_redteam.scoring import score_state
from agent_redteam.targets.state import engagement_id_from_db_path
from agent_redteam.targets.store import EngagementStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", type=Path, help="path to .runs/engagement-<id>.db")
    parser.add_argument("--goal", default=None, help="goal host id to score reachability against")
    parser.add_argument("--optimal-hops", type=int, default=None, help="ground-truth optimal hops")
    parser.add_argument("--engagement-id", default=None, help="override inferred id")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"no such database: {args.db}")

    store = EngagementStore.connect(args.db)
    try:
        engagement_id = engagement_id_from_db_path(args.db, args.engagement_id)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    state = store.load_state(engagement_id)
    scorecard = score_state(
        state,
        goal=args.goal,
        optimal_hops=args.optimal_hops,
        attempts=store.list_attempts(engagement_id),
    )
    print(scorecard.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
