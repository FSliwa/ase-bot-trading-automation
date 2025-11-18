from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from src.infrastructure.logging.logger import get_logger

router = APIRouter(prefix="/api/v1/trial", tags=["trial"])

logger = get_logger(__name__)


class TrialActivationRequest(BaseModel):
    userId: str = Field(..., description="Identifier of the Supabase user")
    email: EmailStr | None = Field(default=None, description="Optional user email")
    language: str = Field(..., min_length=2, max_length=10)
    trialEndsAt: datetime = Field(..., description="ISO timestamp marking trial end")


class TrialActivationResponse(BaseModel):
    message: str = "trial activation recorded"
    status: str = "ok"
    recordedAt: datetime


@router.post(
    "/activate",
    response_model=TrialActivationResponse,
    status_code=status.HTTP_200_OK,
)
async def activate_trial(payload: TrialActivationRequest) -> TrialActivationResponse:
    """Compatibility endpoint used by the frontend to sync trial activation.

    The backend does not yet persist the trial metadata, but we log the
    incoming payload so operators can audit requests. A real implementation can
    extend this handler to persist the data in a dedicated table or trigger
    additional automation.
    """

    try:
        logger.info(
            "Received trial activation",
            extra={
                "user_id": payload.userId,
                "email": payload.email,
                "language": payload.language,
                "trial_ends_at": payload.trialEndsAt.isoformat(),
            },
        )
    except Exception as exc:  # pragma: no cover - defensive logging guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record trial activation",
        ) from exc

    return TrialActivationResponse(recordedAt=datetime.utcnow())
