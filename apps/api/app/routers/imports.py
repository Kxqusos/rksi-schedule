from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.cache import get_cache
from app.schemas.import_schedule import ImportScheduleResponse
from app.services.auth.permissions import Actor, require_editor_actor
from app.services.import_schedule import import_schedule_from_payload
from app.services.import_schedule.mappers import import_result_to_response

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/schedule", response_model=ImportScheduleResponse)
async def import_schedule(
    request: Request,
    actor: Annotated[Actor, Depends(require_editor_actor)],
) -> dict:
    payload = await _read_import_payload(request)
    result = import_schedule_from_payload(
        payload,
        source_path="api:/imports/schedule",
    )
    get_cache().invalidate_all()
    return import_result_to_response(result).model_dump(mode="json")


async def _read_import_payload(request: Request):
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file is None or not hasattr(uploaded_file, "read"):
            raise HTTPException(status_code=400, detail="multipart field 'file' is required")
        raw_payload = await uploaded_file.read()
        try:
            return json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="uploaded file must contain valid JSON") from exc

    try:
        return await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="request body must contain valid JSON") from exc
