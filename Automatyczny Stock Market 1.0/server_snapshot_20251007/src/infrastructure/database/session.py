"""Database session management."""

from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, event
import time

from src.infrastructure.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url.get_secret_value(),
    echo=False,  # Don't log SQL in production
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,  # Test connections before using
    pool_recycle=3600,  # Recycle connections every hour
    pool_timeout=30,  # Connection timeout
    connect_args={
        "server_settings": {
            "application_name": "ase-trading-bot",
            "jit": "off",  # Disable JIT for consistent performance
        },
        "command_timeout": 30,
        "statement_cache_size": 0,  # Disable statement cache for security
    }
)

# Query performance monitoring
@event.listens_for(engine.sync_engine, "before_cursor_execute")
def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Track query start time."""
    context._query_start_time = time.time()

@event.listens_for(engine.sync_engine, "after_cursor_execute") 
def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Track query execution time."""
    if hasattr(context, '_query_start_time'):
        total_time = time.time() - context._query_start_time
        
        # Log slow queries (>100ms)
        if total_time > 0.1:
            from src.infrastructure.logging.logger import get_logger
            logger = get_logger(__name__)
            logger.warning(f"Slow query detected: {total_time:.3f}s - {statement[:100]}...")
            
        # Track metrics (if OpenTelemetry available)
        try:
            from src.infrastructure.observability import db_query_duration
            db_query_duration.record(total_time, {
                "query_type": statement.split()[0].upper() if statement else "UNKNOWN"
            })
        except ImportError:
            pass
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session(user_id: Optional[int] = None) -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get a database session with RLS context."""
    async with AsyncSessionLocal() as session:
        if user_id is not None:
            # Set the current user ID for RLS
            await session.execute(text(f"SET LOCAL app.current_user_id = '{user_id}'"))
        yield session
