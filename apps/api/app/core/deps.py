"""Request-scoped access to the adapter container."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.adapters.registry import Adapters


def get_adapters(request: Request) -> Adapters:
    adapters: Adapters = request.app.state.adapters
    return adapters


AdaptersDep = Annotated[Adapters, Depends(get_adapters)]
