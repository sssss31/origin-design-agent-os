from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


_RANK = {Role.VIEWER: 0, Role.MEMBER: 1, Role.ADMIN: 2}


def has_at_least(actual: Role | str | None, required: Role | str) -> bool:
    if actual is None:
        return False
    return _RANK[Role(actual)] >= _RANK[Role(required)]
