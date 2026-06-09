from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_ENV_LOADED = False


@dataclass(frozen=True, slots=True)
class BootstrapAdminConfig:
    username: str
    display_name: str
    password: str


def load_env_file() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    env_path = Path.cwd() / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    _ENV_LOADED = True


def get_database_url() -> str:
    load_env_file()
    return os.getenv("DATABASE_URL", "sqlite:///schedule-rks.db")


def get_cors_origins() -> list[str]:
    load_env_file()
    raw_origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003,http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002,http://127.0.0.1:3003",
    )
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


def get_auth_secret() -> str:
    load_env_file()
    return os.getenv("AUTH_SECRET", "schedule-rks-dev-secret")


def get_bootstrap_admin_config() -> BootstrapAdminConfig | None:
    load_env_file()
    username = os.getenv("ADMIN_USERNAME", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "")
    display_name = os.getenv("ADMIN_DISPLAY_NAME", username).strip()
    if not username or not password:
        return None
    return BootstrapAdminConfig(
        username=username,
        display_name=display_name or username,
        password=password,
    )
