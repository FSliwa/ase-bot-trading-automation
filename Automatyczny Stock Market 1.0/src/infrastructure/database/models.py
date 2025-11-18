from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="user")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    sessions = relationship(
        "SessionModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    api_keys = relationship(
        "APIKeyModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def touch(self) -> None:
        self.updated_at = datetime.utcnow()


class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("UserModel", back_populates="sessions")


class APIKeyModel(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exchange = Column(String(64), nullable=False)
    access_key = Column(String(255), nullable=False)
    secret_key = Column(String(255), nullable=False)
    passphrase = Column(String(255), nullable=True)
    label = Column(String(120), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("UserModel", back_populates="api_keys")

    __table_args__ = (
        UniqueConstraint("user_id", "exchange", name="uq_api_keys_user_exchange"),
        Index("ix_api_keys_user_exchange", "user_id", "exchange"),
    )


class TradeOrderModel(Base):
    __tablename__ = "trade_orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exchange = Column(String(64), nullable=False)
    symbol = Column(String(120), nullable=False)
    side = Column(String(8), nullable=False)
    order_type = Column(String(16), nullable=False)
    quantity = Column(Float, nullable=False)
    executed_quantity = Column(Float, nullable=True)
    price = Column(Float, nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    external_id = Column(String(255), nullable=True, index=True)
    raw_response = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("UserModel")
