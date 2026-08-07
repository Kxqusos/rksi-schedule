from __future__ import annotations

from datetime import date as Date
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import Text, cast, func, or_, select

from app.models import AuditLog
from app.services.audit import labels


def get_audit_entries(
    session,
    *,
    query: str | None,
    entity_types: list[str] | None,
    date_from: Date | None,
    date_to: Date | None,
    limit: int,
    offset: int,
) -> tuple[list[AuditLog], int]:
    conditions = _conditions(query=query, entity_types=entity_types, date_from=date_from, date_to=date_to)

    total = session.scalar(select(func.count(AuditLog.id)).where(*conditions)) or 0
    entries = session.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(entries), int(total)


def _conditions(
    *,
    query: str | None,
    entity_types: list[str] | None,
    date_from: Date | None,
    date_to: Date | None,
) -> list:
    conditions = []
    if entity_types:
        conditions.append(AuditLog.entity_type.in_(entity_types))
    if date_from is not None:
        conditions.append(AuditLog.created_at >= _day_start(date_from))
    if date_to is not None:
        # date_to is inclusive, so compare against the start of the next day.
        conditions.append(AuditLog.created_at < _day_start(date_to + timedelta(days=1)))
    if query:
        conditions.append(_search_condition(query))
    return conditions


def _search_condition(query: str):
    """Match the query against what the user actually sees on screen.

    actor_name and payload cover names and values stored verbatim ("305",
    "ИС-21"). The visible Russian words for entity type and action exist only in
    labels.py, so those are resolved to column values and OR-ed in.
    """
    normalized = query.strip().lower()
    pattern = f"%{normalized}%"
    clauses = [
        AuditLog.actor_name.ilike(pattern),
        cast(AuditLog.payload, Text).ilike(pattern),
    ]

    matched_entity_types = labels.match_entity_types(normalized)
    if matched_entity_types:
        clauses.append(AuditLog.entity_type.in_(matched_entity_types))
    matched_actions = labels.match_actions(normalized)
    if matched_actions:
        clauses.append(AuditLog.action.in_(matched_actions))
    return or_(*clauses)


def _day_start(day: Date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)
