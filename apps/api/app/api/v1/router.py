from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import agents, auth, files, health, me, projects, workspaces
from app.api.v1.admin import admin_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(workspaces.router)
api_router.include_router(projects.router)
api_router.include_router(agents.router)
api_router.include_router(admin_router())
api_router.include_router(files.router)
