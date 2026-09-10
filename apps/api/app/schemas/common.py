from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import inspect

# Syntactic email check only. `EmailStr` rejects reserved domains such as `.local`, which
# internal deployments legitimately use; deliverability is not our concern at the API edge.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    ),
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str


def from_orm[T: BaseModel](schema: type[T], obj: Any, **extra: Any) -> T:
    """Build a response schema from a loaded ORM row plus computed fields (e.g. `my_role`).

    Reads mapped column attributes only, so relationships are never lazy-loaded from a request
    handler (which would be implicit I/O under the async session).
    """
    data = {attr.key: getattr(obj, attr.key) for attr in inspect(obj).mapper.column_attrs}
    data.update(extra)
    return schema.model_validate(data)
