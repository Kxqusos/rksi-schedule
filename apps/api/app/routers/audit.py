from __future__ import annotations

from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.audit import AuditPageResponse
from app.services.audit import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, list_audit_entries, mappers
from app.services.auth.permissions import Actor, require_editor_actor

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditPageResponse)
def get_audit_entries(
    actor: Annotated[Actor, Depends(require_editor_actor)],
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    entity_type: Annotated[list[str] | None, Query()] = None,
    date_from: Date | None = None,
    date_to: Date | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    page = list_audit_entries(
        session,
        query=q,
        entity_types=entity_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return mappers.audit_page_to_response(page).model_dump(mode="json")
