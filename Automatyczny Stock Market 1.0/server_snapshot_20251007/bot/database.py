"""
Supabase database connection manager.
Handles connection pooling and session management.
"""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
import logging

from .models import Base

logger = logging.getLogger(__name__)

# Database URL resolution
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
ALLOW_SQLITE_FALLBACK = os.getenv("ALLOW_SQLITE_FALLBACK", "false").lower() == "true"

if not SUPABASE_DB_URL:
    if ALLOW_SQLITE_FALLBACK:
        SUPABASE_DB_URL = "sqlite:///trading.db"
        logger.warning("⚠️  No SUPABASE_DB_URL found, using SQLite fallback")
    else:
        raise ValueError(
            "SUPABASE_DB_URL or DATABASE_URL environment variable must be set. "
            "Set ALLOW_SQLITE_FALLBACK=true to use SQLite for local development."
        )

# Create engine with appropriate settings
if SUPABASE_DB_URL.startswith("postgresql"):
    # PostgreSQL/Supabase settings
    engine = create_engine(
        SUPABASE_DB_URL,
        pool_pre_ping=True,  # Verify connections before using
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,  # Recycle connections after 1 hour
        echo=False,  # Set to True for SQL query logging
    )
    logger.info(f"✓ Connected to Supabase PostgreSQL: {SUPABASE_DB_URL.split('@')[1].split('/')[0]}")
else:
    # SQLite settings
    engine = create_engine(
        SUPABASE_DB_URL,
        poolclass=NullPool,  # SQLite doesn't need connection pooling
        echo=False,
    )
    logger.info(f"✓ Using SQLite database: {SUPABASE_DB_URL}")

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class DatabaseManager:
    """
    Context manager for database sessions.
    
    Usage:
        with DatabaseManager() as db:
            user = db.session.query(Profile).filter_by(username="test").first()
            db.session.add(new_trade)
            db.session.commit()
    """
    
    def __init__(self):
        self.session: Session = SessionLocal()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logger.error(f"Database error: {exc_val}")
            self.session.rollback()
        self.session.close()
        return False  # Don't suppress exceptions
    
    def commit(self):
        """Commit current transaction."""
        try:
            self.session.commit()
        except Exception as e:
            logger.error(f"Commit failed: {e}")
            self.session.rollback()
            raise
    
    def rollback(self):
        """Rollback current transaction."""
        self.session.rollback()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Alternative session context manager that yields session directly.
    
    Usage:
        with get_db_session() as session:
            user = session.query(Profile).filter_by(username="test").first()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"Database session error: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def create_all_tables():
    """
    Create all database tables.
    This should be called during application initialization.
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✓ All database tables created/verified")
    except Exception as e:
        logger.error(f"✗ Failed to create tables: {e}")
        raise


def drop_all_tables():
    """
    Drop all database tables.
    ⚠️ USE WITH CAUTION - This will delete all data!
    """
    try:
        Base.metadata.drop_all(bind=engine)
        logger.warning("⚠️  All database tables dropped")
    except Exception as e:
        logger.error(f"✗ Failed to drop tables: {e}")
        raise


def check_connection() -> bool:
    """
    Test database connectivity.
    Returns True if connection is successful, False otherwise.
    """
    try:
        with get_db_session() as session:
            session.execute("SELECT 1")
        logger.info("✓ Database connection successful")
        return True
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        return False


# Event listeners for connection management
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Log new database connections."""
    logger.debug("New database connection established")


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """Verify connection is alive on checkout."""
    pass  # pool_pre_ping handles this


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_conn, connection_record):
    """Log connection return to pool."""
    logger.debug("Connection returned to pool")
