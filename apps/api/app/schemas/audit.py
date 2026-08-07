from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditEntryResponse(BaseModel):
    id: int
    created_at: datetime
    actor_name: str
    actor_role: str
    actor_role_label: str
    entity_type: str
    entity_label: str
    action: str
    summary: str


class AuditPageResponse(BaseModel):
    items: list[AuditEntryResponse]
    total: int
    limit: int
    offset: int
