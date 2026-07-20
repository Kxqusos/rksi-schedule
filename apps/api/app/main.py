from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.cache import init_cache
from app.core.config import get_cors_origins, get_database_url, get_redis_url
from app.db.engine import dispose_engine, init_engine
from app.routers.auth import router as auth_router
from app.routers.groups import router as groups_router
from app.routers.imports import router as imports_router
from app.routers.rooms import router as rooms_router
from app.routers.schedule import router as schedule_router
from app.routers.teachers import router as teachers_router
from app.routers.time_profiles import router as time_profiles_router
from app.routers.users import router as users_router
from app.services.bootstrap import bootstrap_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = getattr(app.state, "database_url", None) or get_database_url()
    init_engine(database_url)
    bootstrap_admin()
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
app.include_router(imports_router)
app.include_router(rooms_router)
app.include_router(schedule_router)
app.include_router(teachers_router)
app.include_router(time_profiles_router)
app.include_router(users_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
