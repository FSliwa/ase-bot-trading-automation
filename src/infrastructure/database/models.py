"""SQLAlchemy database models."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserModel(Base):
    """User database model."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="user")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)

    # Relationships
    sessions = relationship("SessionModel", back_populates="user", cascade="all, delete-orphan")
    trading_bots = relationship(
        "TradingBotModel", back_populates="user", cascade="all, delete-orphan"
    )
    transactions = relationship("TransactionModel", back_populates="user")

    # Indexes for performance
    __table_args__ = (
        Index("idx_user_email_active", "email", "is_active"),
        Index("idx_user_created_at", "created_at"),
    )


class SessionModel(Base):
    """User session database model."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token = Column(String(255), unique=True, nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    user = relationship("UserModel", back_populates="sessions")

    # Indexes
    __table_args__ = (
        Index("idx_session_token_active", "token", "is_active"),
        Index("idx_session_user_active", "user_id", "is_active"),
        Index("idx_session_expires", "expires_at"),
    )


class TradingBotModel(Base):
    """Trading bot database model."""

    __tablename__ = "trading_bots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(100), nullable=False)
    strategy_type = Column(String(50), nullable=False)
    status = Column(String(20), default="inactive", nullable=False)
    config = Column(Text, nullable=False)  # JSON configuration
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_run_at = Column(DateTime, nullable=True)

    # Performance metrics
    total_profit = Column(Float, default=0.0, nullable=False)
    win_rate = Column(Float, default=0.0, nullable=False)
    total_trades = Column(Integer, default=0, nullable=False)

    # Relationships
    user = relationship("UserModel", back_populates="trading_bots")
    transactions = relationship("TransactionModel", back_populates="bot")

    # Indexes
    __table_args__ = (
        Index("idx_bot_user_status", "user_id", "status"),
        Index("idx_bot_created_at", "created_at"),
        UniqueConstraint("user_id", "name", name="uq_user_bot_name"),
    )


class TransactionModel(Base):
    """Transaction database model."""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    bot_id = Column(Integer, ForeignKey("trading_bots.id"), nullable=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)  # buy/sell
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    total = Column(Float, nullable=False)
    fee = Column(Float, default=0.0, nullable=False)
    profit_loss = Column(Float, nullable=True)
    status = Column(String(20), default="pending", nullable=False)
    executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("UserModel", back_populates="transactions")
    bot = relationship("TradingBotModel", back_populates="transactions")

    # Indexes
    __table_args__ = (
        Index("idx_transaction_user_created", "user_id", "created_at"),
        Index("idx_transaction_symbol_created", "symbol", "created_at"),
        Index("idx_transaction_status", "status"),
    )
