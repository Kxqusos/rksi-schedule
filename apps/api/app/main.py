from dataclasses import asdict
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.cache import init_cache
from app.core.config import get_cors_origins, get_database_url, get_redis_url
from app.db.engine import dispose_engine, init_engine
from app.routers.auth import router as auth_router
from app.routers.groups import router as groups_router
from app.routers.rooms import router as rooms_router
from app.routers.schedule import router as schedule_router
from app.routers.teachers import router as teachers_router
from app.routers.time_profiles import router as time_profiles_router
from app.routers.users import router as users_router
from app.schemas.import_schedule import ImportScheduleResponse
from app.services.bootstrap import bootstrap_admin
from app.services.import_schedule import import_schedule_from_payload


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = getattr(app.state, "database_url", None) or get_database_url()
    init_engine(database_url)
    bootstrap_admin(database_url)
    init_cache(get_redis_url())
    yield
    dispose_engine()


app = FastAPI(title="Schedule RKSI API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(groups_router)
app.include_router(rooms_router)
app.include_router(schedule_router)
app.include_router(teachers_router)
app.include_router(time_profiles_router)
app.include_router(users_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/imports/schedule", response_model=ImportScheduleResponse)
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
