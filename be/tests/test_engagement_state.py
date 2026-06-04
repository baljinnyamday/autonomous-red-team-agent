from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.topology import Transport


def test_merge_runtime_ignores_unknown_hosts() -> None:
    seed = EngagementState(
        engagement_id="eng-1",
        hosts={"kali": HostRuntime(transport=Transport.SSH_PENDING, address="10.0.0.1")},
    )
    persisted = EngagementState(
        engagement_id="eng-1",
        hosts={
            "stale": HostRuntime(
                transport=Transport.RUNNER,
                runner_endpoint="http://evil:8765",
            ),
            "kali": HostRuntime(
                transport=Transport.RUNNER,
                runner_endpoint="http://127.0.0.1:8765",
            ),
        },
    )
    merged = seed.merge_runtime(persisted)
    assert "stale" not in merged.hosts
    assert merged.hosts["kali"].transport is Transport.RUNNER
    assert merged.hosts["kali"].runner_endpoint == "http://127.0.0.1:8765"


def test_merge_runtime_rejects_engagement_id_mismatch() -> None:
    seed = EngagementState(
        engagement_id="eng-a",
        hosts={"operator": HostRuntime(transport=Transport.LOCAL)},
    )
    persisted = EngagementState(
        engagement_id="eng-b",
        hosts={
            "operator": HostRuntime(
                transport=Transport.RUNNER,
                runner_endpoint="http://127.0.0.1:8765",
            )
        },
    )
    merged = seed.merge_runtime(persisted)
    assert merged.hosts["operator"].transport is Transport.LOCAL
