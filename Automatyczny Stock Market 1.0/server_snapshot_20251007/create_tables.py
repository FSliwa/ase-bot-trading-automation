#!/usr/bin/env python3
"""Create database tables directly using SQLAlchemy."""

import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from src.infrastructure.database.models import Base

async def create_tables():
    """Create all database tables."""
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@postgres:5432/trading_bot")
    
    engine = create_async_engine(DATABASE_URL, echo=True)
    
    async with engine.begin() as conn:
        # Drop all tables first
        await conn.run_sync(Base.metadata.drop_all)
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    
    await engine.dispose()
    print("✅ Database tables created successfully!")

if __name__ == "__main__":
    asyncio.run(create_tables())
