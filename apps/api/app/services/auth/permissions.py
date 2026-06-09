from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException


EDITOR_ROLES = {"operator", "admin"}
ADMIN_ROLE = "admin"


@dataclass(frozen=True, slots=True)
class Actor:
    role: str
    name: str


def require_editor_actor(
    role: Annotated[str | None, Header(alias="X-Role")] = None,
    actor: Annotated[str | None, Header(alias="X-Actor")] = None,
) -> Actor:
    if role not in EDITOR_ROLES:
        raise HTTPException(status_code=403, detail="operator or admin role is required")
    return Actor(role=role, name=actor or role)


def require_admin_actor(
    role: Annotated[str | None, Header(alias="X-Role")] = None,
    actor: Annotated[str | None, Header(alias="X-Actor")] = None,
) -> Actor:
    if role != ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="admin role is required")
    return Actor(role=role, name=actor or role)
