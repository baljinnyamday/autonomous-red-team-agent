from pydantic import BaseModel, Field


class TargetScope(BaseModel):
    """Declarative scope for an authorized engagement."""

    engagement_id: str
    hosts: list[str] = Field(default_factory=list)
    notes: str | None = None
