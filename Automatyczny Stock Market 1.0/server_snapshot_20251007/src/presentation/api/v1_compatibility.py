"""Backward compatibility endpoints for V1 API."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from src.application.services.user_service import UserService
from src.presentation.api.dependencies import get_user_service

router = APIRouter(tags=["v1-compatibility"])


class V1LoginRequest(BaseModel):
    """Login request for backward compatibility."""
    email: EmailStr
    password: str


class V1LoginResponse(BaseModel):
    """Login response for backward compatibility."""
    access_token: str
    token_type: str = "bearer"


@router.post("/api/login", response_model=V1LoginResponse)
async def login_v1(
    request: V1LoginRequest,
    user_service: UserService = Depends(get_user_service),
):
    """
    Backward compatibility endpoint for V1 login.
    Redirects to V2 login logic.
    """
    try:
        user, token = await user_service.authenticate_user(
            email=request.email,
            password=request.password
        )
        return V1LoginResponse(access_token=token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
