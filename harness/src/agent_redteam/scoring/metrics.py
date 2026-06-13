"""Benchmark metrics over a finished engagement's state.

All metrics derive from the recorded `EngagementState` and its NetworkX view, so
a run is scored from the same SQLite topology the agent built. No live execution.
"""

from __future__ import annotations

import networkx as nx
from pydantic import BaseModel

from agent_redteam.targets.graph import OPERATOR_HOST_ID
from agent_redteam.targets.nx_graph import build_digraph, reachable_from, shortest_path
from agent_redteam.targets.state import EngagementState
from agent_redteam.targets.topology import AttemptRecord


class Scorecard(BaseModel):
    engagement_id: str
    goal: str | None
    goal_reached: bool
    hops_to_goal: int | None
    path_efficiency: float | None
    coverage: float
    hosts_total: int
    hosts_with_findings: int
    attempts_total: int
    attempts_blocked: int
    wasted_attempt_rate: float


def score_state(
    state: EngagementState,
    *,
    goal: str | None = None,
    optimal_hops: int | None = None,
    attempts: list[AttemptRecord] | None = None,
) -> Scorecard:
    graph = build_digraph(state)
    path = shortest_path(graph, OPERATOR_HOST_ID, goal) if goal else None
    hops = (len(path) - 1) if path else None
    hosts = [host_id for host_id in state.hosts if host_id != OPERATOR_HOST_ID]
    with_findings = sum(
        1 for host_id in hosts if state.hosts[host_id].services or state.hosts[host_id].credentials
    )
    attempts = attempts or []
    blocked = 0
    wasted = 0
    for attempt in attempts:
        if attempt.outcome == "blocked":
            blocked += 1
            wasted += 1
        elif attempt.outcome == "failure":
            wasted += 1
    path_efficiency = None
    if hops is not None and optimal_hops:
        path_efficiency = optimal_hops / hops
    return Scorecard(
        engagement_id=state.engagement_id,
        goal=goal,
        goal_reached=goal_reached(state, goal, graph=graph),
        hops_to_goal=hops,
        path_efficiency=path_efficiency,
        coverage=(with_findings / len(hosts)) if hosts else 0.0,
        hosts_total=len(state.hosts),
        hosts_with_findings=with_findings,
        attempts_total=len(attempts),
        attempts_blocked=blocked,
        wasted_attempt_rate=(wasted / len(attempts)) if attempts else 0.0,
    )


def goal_reached(
    state: EngagementState,
    goal: str | None,
    *,
    graph: nx.DiGraph | None = None,
) -> bool:
    """True when the goal host exists and is reachable from the operator."""
    if goal is None or goal not in state.hosts:
        return False
    if graph is None:
        graph = build_digraph(state)
    return goal in reachable_from(graph, OPERATOR_HOST_ID)
