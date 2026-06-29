from __future__ import annotations

from app.models import User
from app.schemas.user import UserResponse


def user_to_response(user: User, role_name: str) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=role_name,
        is_active=user.is_active,
        created_at=user.created_at,
    )
