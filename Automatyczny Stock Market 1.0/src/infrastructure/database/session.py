from collections.abc import AsyncGenerator
import os
import warnings

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

APP_ENV = os.getenv("APP_ENV", "development").lower()
DATABASE_URL = os.getenv("DATABASE_URL")
PLACEHOLDER_URL = "postgresql+asyncpg://user:password@localhost/db"

if not DATABASE_URL or DATABASE_URL == PLACEHOLDER_URL:
    if APP_ENV == "development":
        DATABASE_URL = os.getenv(
            "DEV_DATABASE_URL",
            "postgresql+asyncpg://localhost/trading_bot",
        )
        warnings.warn(
            "DATABASE_URL is not configured; falling back to development default. "
            "Do not use this fallback in production.",
            RuntimeWarning,
        )
    else:
        raise RuntimeError(
            "DATABASE_URL environment variable must be set with secure credentials "
            "when APP_ENV is not development."
        )

if "user:password" in DATABASE_URL and APP_ENV != "development":
    raise RuntimeError("DATABASE_URL uses placeholder credentials; please provide secure values.")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal: sessionmaker[AsyncSession] = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a scoped async session."""

    async with AsyncSessionLocal() as session:
        yield session
