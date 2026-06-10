from agent_redteam import __version__
from agent_redteam.schemas.common import HealthResponse


def health_check() -> HealthResponse:
    return HealthResponse(version=__version__)
