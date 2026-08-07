from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date

from app.models import AuditLog
from app.services.audit import repository

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class AuditPage:
    entries: list[AuditLog]
    total: int
    limit: int
    offset: int


def list_audit_entries(
    session,
    *,
    query: str | None = None,
    entity_types: list[str] | None = None,
    date_from: Date | None = None,
    date_to: Date | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> AuditPage:
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
    entries, total = repository.get_audit_entries(
        session,
        query=query,
        entity_types=entity_types,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return AuditPage(entries=entries, total=total, limit=limit, offset=offset)
