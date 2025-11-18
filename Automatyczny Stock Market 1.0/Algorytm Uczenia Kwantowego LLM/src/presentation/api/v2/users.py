"""User API routes with Pydantic validation."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, validator

from src.application.services.user_service import UserService
from src.domain.entities.user import User
from src.presentation.api.dependencies import get_current_user, get_user_service, rate_limiter

router = APIRouter(prefix="/api/v2/users", tags=["users"])
security = HTTPBearer()


class UserRegistrationRequest(BaseModel):
    """User registration request model with strict validation."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=8, max_length=128)

    @validator("password")
    def validate_password(cls, v):
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v

    class Config:
        """Pydantic config."""

        schema_extra = {
            "example": {
                "email": "user@example.com",
                "username": "john_doe",
                "password": "SecureP@ss123",
            }
        }


class UserLoginRequest(BaseModel):
    """User login request model."""

    email: EmailStr
    password: str = Field(..., min_length=1)

    class Config:
        """Pydantic config."""

        schema_extra = {"example": {"email": "user@example.com", "password": "SecureP@ss123"}}


class UserResponse(BaseModel):
    """User response model."""

    id: int
    email: str
    username: str
    role: str
    is_active: bool
    created_at: datetime
    last_login: datetime | None

    class Config:
        """Pydantic config."""

        orm_mode = True


class TokenResponse(BaseModel):
    """Token response model."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    user: UserResponse


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limiter(max_calls=5, time_window=3600))],
)
async def register_user(
    request: UserRegistrationRequest, user_service: UserService = Depends(get_user_service)
):
    """Register a new user with validation and rate limiting."""
    try:
        user = await user_service.register_user(
            email=request.email, username=request.username, password=request.password
        )
        return UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            role=user.role.value,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limiter(max_calls=10, time_window=3600))],
)
async def login_user(
    request: UserLoginRequest, user_service: UserService = Depends(get_user_service)
):
    """Authenticate user and return access token."""
    try:
        user, token = await user_service.authenticate_user(
            email=request.email, password=request.password
        )
        return TokenResponse(
            access_token=token,
            user=UserResponse(
                id=user.id,
                email=user.email,
                username=user.username,
                role=user.role.value,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login=user.last_login,
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from e


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user information."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        role=current_user.role.value,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        last_login=current_user.last_login,
    )


@router.post("/logout")
async def logout_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_service: UserService = Depends(get_user_service),
):
    """Logout current user by invalidating session."""
    success = await user_service.logout_user(credentials.credentials)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to logout")
    return {"message": "Successfully logged out"}
