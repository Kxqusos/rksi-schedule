from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.core.config import get_auth_secret

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 210_000
TOKEN_TTL_SECONDS = 12 * 60 * 60


class InvalidTokenError(Exception):
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "$".join(
        [
            PASSWORD_ALGORITHM,
            str(PASSWORD_ITERATIONS),
            _b64encode(salt),
            _b64encode(digest),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = _b64decode(salt_text)
        expected_digest = _b64decode(digest_text)
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual_digest, expected_digest)


def create_access_token(payload: dict[str, Any]) -> str:
    now = int(time.time())
    token_payload = {**payload, "iat": now, "exp": now + TOKEN_TTL_SECONDS}
    payload_text = _b64encode(json.dumps(token_payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signature = _sign(payload_text)
    return f"{payload_text}.{signature}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload_text, signature = token.split(".", 1)
    except ValueError as exc:
        raise InvalidTokenError() from exc

    expected_signature = _sign(payload_text)
    if not hmac.compare_digest(signature, expected_signature):
        raise InvalidTokenError()

    try:
        payload = json.loads(_b64decode(payload_text))
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidTokenError() from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise InvalidTokenError()
    return payload


def _sign(payload_text: str) -> str:
    digest = hmac.new(get_auth_secret().encode("utf-8"), payload_text.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
