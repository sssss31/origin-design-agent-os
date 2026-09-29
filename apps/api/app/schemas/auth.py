from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import Email
from app.schemas.identity import MeResponse


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    me: MeResponse | None = None  # returned by /login so the client skips a /me round trip
