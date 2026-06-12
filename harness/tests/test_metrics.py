from agent_redteam.scoring.metrics import goal_reached, score_state
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.topology import CredentialFinding, ServiceFinding, Transport


def _state() -> EngagementState:
    return EngagementState(
        engagement_id="eng-1",
        hosts={
            "operator": HostRuntime(transport=Transport.LOCAL),
            "web": HostRuntime(
                transport=Transport.REMOTE,
                address="10.0.0.10",
                discovered_from="operator",
                services=[ServiceFinding(port=80, protocol="tcp", product="http")],
            ),
            "db": HostRuntime(
                transport=Transport.REMOTE,
                address="10.0.0.11",
                discovered_from="web",
                credentials=[CredentialFinding(username="root", secret="x")],
            ),
            "isolated": HostRuntime(transport=Transport.REMOTE, address="10.0.0.99"),
        },
    )


def test_goal_reached_when_goal_reachable_from_operator() -> None:
    assert goal_reached(_state(), "db") is True


def test_goal_not_reached_when_unknown_or_missing() -> None:
    assert goal_reached(_state(), "ghost") is False
    assert goal_reached(_state(), None) is False


def test_score_state_reports_hops_coverage_and_efficiency() -> None:
    card = score_state(_state(), goal="db", optimal_hops=1)
    assert card.goal_reached is True
    assert card.hops_to_goal == 2
    assert card.path_efficiency == 0.5  # optimal 1 / discovered 2
    # web + db have findings; isolated does not -> 2 of 3 non-operator hosts
    assert card.hosts_with_findings == 2
    assert round(card.coverage, 3) == round(2 / 3, 3)
