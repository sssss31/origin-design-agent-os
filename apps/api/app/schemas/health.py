from __future__ import annotations

from pydantic import BaseModel


class HealthOut(BaseModel):
    status: str
    name: str
    version: str
    env: str


class ReadyOut(BaseModel):
    status: str
    checks: dict[str, bool]
