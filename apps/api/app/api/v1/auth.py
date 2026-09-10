from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.core.authz import DB, Config
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, TokenResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _client(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("user-agent"), request.client.host if request.client else None


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, session: DB, settings: Config) -> TokenResponse:
    ua, ip = _client(request)
    pair = await AuthService(session, settings).login(
        email=body.email, password=body.password, user_agent=ua, ip=ip
    )
    return TokenResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token, expires_in=pair.expires_in
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request, session: DB, settings: Config) -> TokenResponse:
    ua, ip = _client(request)
    pair = await AuthService(session, settings).refresh(
        refresh_token=body.refresh_token, user_agent=ua, ip=ip
    )
    return TokenResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token, expires_in=pair.expires_in
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest, session: DB, settings: Config) -> None:
    await AuthService(session, settings).logout(refresh_token=body.refresh_token)
