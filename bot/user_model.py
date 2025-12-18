"""User model for Supabase authentication."""

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func
from bot.db import Base


class User(Base):  # type: ignore[misc]
    """User account model."""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    role = Column(String(20), nullable=False, default="user")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
