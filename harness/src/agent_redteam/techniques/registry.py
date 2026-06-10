from pydantic import BaseModel


class Technique(BaseModel):
    id: str
    name: str
    description: str
    mitre_attack_id: str | None = None


class TechniqueRegistry:
    """Register and look up authorized test techniques / playbooks."""

    def __init__(self) -> None:
        self._techniques: dict[str, Technique] = {}

    def register(self, technique: Technique) -> None:
        self._techniques[technique.id] = technique

    def get(self, technique_id: str) -> Technique | None:
        return self._techniques.get(technique_id)

    def list_all(self) -> list[Technique]:
        return list(self._techniques.values())
