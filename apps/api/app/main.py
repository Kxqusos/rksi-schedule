from dataclasses import asdict
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_cors_origins, get_database_url
from app.routers.auth import router as auth_router
from app.routers.rooms import router as rooms_router
from app.routers.schedule import router as schedule_router
from app.routers.teachers import router as teachers_router
from app.routers.users import router as users_router
from app.services.bootstrap import bootstrap_admin
from app.services.import_schedule import import_schedule_from_payload


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap_admin(get_database_url())
    yield


app = FastAPI(title="Schedule RKS API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(rooms_router)
app.include_router(schedule_router)
app.include_router(teachers_router)
app.include_router(users_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/imports/schedule")
async def import_schedule(request: Request) -> dict[str, int]:
    database_url = getattr(request.app.state, "database_url", None) or get_database_url()
    payload = await _read_import_payload(request)
    result = import_schedule_from_payload(
        payload,
        database_url=database_url,
        source_path="api:/imports/schedule",
    )
    return asdict(result)


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
