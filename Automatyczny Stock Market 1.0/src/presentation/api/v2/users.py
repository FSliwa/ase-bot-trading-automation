from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from src.application.services.user_service import UserService
from src.domain.entities.user import User
from src.presentation.api.dependencies import get_current_user, get_user_service, security

router = APIRouter(prefix="/api/v2/users", tags=["users"])


class LogoutResponse(BaseModel):
    message: str


@router.post("/logout", response_model=LogoutResponse)
async def logout_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_service: UserService = Depends(get_user_service),
) -> LogoutResponse:
    """Logout current user by invalidating session."""

    success = await user_service.logout_user(credentials.credentials)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to logout"
        )
    return LogoutResponse(message="Successfully logged out")


@router.get("/me", response_model=dict)
async def get_profile(current_user: User = Depends(get_current_user)) -> dict[str, object]:
    """Return the authenticated user's profile."""

    return {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "role": current_user.role.value,
        "is_active": current_user.is_active,
    }
