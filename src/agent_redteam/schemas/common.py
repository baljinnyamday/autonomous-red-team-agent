from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


class MessageResponse(BaseModel):
    message: str
