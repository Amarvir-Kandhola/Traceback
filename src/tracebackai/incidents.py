"""Incident model: the investigation that evidence is attached to."""

from pydantic import AwareDatetime, BaseModel, ConfigDict


class Incident(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    description: str
    created_at: AwareDatetime
