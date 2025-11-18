"""
Complete Supabase database models matching frontend schema.
This file replaces bot/db.py and bot/user_model.py with unified models.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, Column, Date, DateTime, 
    ForeignKey, Integer, JSON, Numeric, String, Text, func
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid as uuid_pkg

Base = declarative_base()


# ============================================================================
# USER & AUTH MODELS (auth.users schema)
# ============================================================================

class Profile(Base):
    """User profile - references auth.users from Supabase Auth."""
    __tablename__ = "profiles"
    __table_args__ = {"schema": "public"}
    
    user_id = Column(UUID(as_uuid=True), primary_key=True)
    username = Column(Text, unique=True, nullable=True)
    email = Column(Text, nullable=True)
    full_name = Column(Text, nullable=True)
    first_name = Column(Text, nullable=True)
    last_name = Column(Text, nullable=True)
    phone = Column(Text, nullable=True)  # +48[9 digits]
    
    # Subscription info
    subscription_tier = Column(
        Text, 
        nullable=False, 
        default="free",
        server_default="free"
    )  # free, trial, pro, enterprise
    subscription_status = Column(
        Text, 
        nullable=False, 
        default="inactive",
        server_default="inactive"
    )  # active, inactive, cancelled, past_due
    trial_started_at = Column(DateTime(timezone=True), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    trial_origin = Column(Text, nullable=True)
    
    # Stripe integration
    stripe_customer_id = Column(Text, unique=True, nullable=True)
    stripe_subscription_id = Column(Text, nullable=True)
    stripe_price_id = Column(Text, nullable=True)
    stripe_session_id = Column(Text, nullable=True)
    
    # User preferences
    is_first_login = Column(Boolean, nullable=False, default=True, server_default="true")
    preferred_language = Column(Text, nullable=False, default="EN", server_default="EN")
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationships
    api_keys = relationship("APIKey", back_populates="profile")
    portfolios = relationship("Portfolio", back_populates="profile")
    trades = relationship("Trade", back_populates="profile")
    trading_settings = relationship("TradingSettings", back_populates="profile")
    notifications = relationship("Notification", back_populates="profile")
    ai_insights = relationship("AIInsight", back_populates="profile")
    market_alerts = relationship("MarketAlert", back_populates="profile")
    user_activities = relationship("UserActivity", back_populates="profile")


class UserSession(Base):
    """User session tracking."""
    __tablename__ = "user_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    session_token = Column(Text, nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    last_activity = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())


class AuditLog(Base):
    """Audit log for tracking changes."""
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(Text, nullable=False)
    table_name = Column(Text, nullable=True)
    record_id = Column(UUID(as_uuid=True), nullable=True)
    old_values = Column(JSONB, nullable=True)
    new_values = Column(JSONB, nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())


# ============================================================================
# EXCHANGE & API MODELS
# ============================================================================

class APIKey(Base):
    """Encrypted exchange API keys."""
    __tablename__ = "api_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    exchange = Column(Text, nullable=False)  # USER-DEFINED enum in schema
    encrypted_api_key = Column(Text, nullable=False)
    encrypted_api_secret = Column(Text, nullable=False)
    passphrase = Column(Text, nullable=True)
    is_testnet = Column(Boolean, nullable=True, default=True)
    is_active = Column(Boolean, nullable=True, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationship
    profile = relationship("Profile", back_populates="api_keys")


# ============================================================================
# TRADING MODELS
# ============================================================================

class Portfolio(Base):
    """User portfolio holdings per exchange/symbol."""
    __tablename__ = "portfolios"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    exchange = Column(Text, nullable=False)  # USER-DEFINED enum
    symbol = Column(Text, nullable=False)
    balance = Column(Numeric, nullable=True, default=0)
    locked_balance = Column(Numeric, nullable=True, default=0)
    avg_buy_price = Column(Numeric, nullable=True, default=0)
    total_invested = Column(Numeric, nullable=True, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationship
    profile = relationship("Profile", back_populates="portfolios")


class PortfolioPerformance(Base):
    """Daily portfolio performance snapshots."""
    __tablename__ = "portfolio_performance"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    portfolio_value = Column(Numeric, nullable=False)
    realized_profit = Column(Numeric, nullable=False, default=0)
    unrealized_profit = Column(Numeric, nullable=False, default=0)
    total_profit = Column(Numeric, nullable=False, default=0)
    daily_change = Column(Numeric, nullable=True)
    daily_change_percentage = Column(Numeric, nullable=True)
    recorded_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Trade(Base):
    """Trade execution records."""
    __tablename__ = "trades"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    exchange = Column(Text, nullable=False)  # USER-DEFINED enum
    symbol = Column(Text, nullable=False)
    trade_type = Column(Text, nullable=False)  # USER-DEFINED enum (buy/sell)
    amount = Column(Numeric, nullable=False)
    price = Column(Numeric, nullable=False)
    fee = Column(Numeric, nullable=True, default=0)
    fee_currency = Column(Text, nullable=True, default="USDT", server_default="USDT")
    status = Column(Text, nullable=True, default="pending")  # pending, filled, cancelled
    exchange_order_id = Column(Text, nullable=True)
    strategy_name = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationship
    profile = relationship("Profile", back_populates="trades")


class TradingSettings(Base):
    """User trading configuration."""
    __tablename__ = "trading_settings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    exchange = Column(Text, nullable=False)  # USER-DEFINED enum
    is_trading_enabled = Column(Boolean, nullable=True, default=False)
    max_daily_loss = Column(Numeric, nullable=True, default=100)
    max_position_size = Column(Numeric, nullable=True, default=1000)
    risk_level = Column(
        Integer, 
        nullable=True, 
        default=3,
        server_default="3"
    )  # 1-5
    preferred_pairs = Column(
        ARRAY(Text), 
        nullable=True,
        default=["BTC/USDT", "ETH/USDT"]
    )
    stop_loss_percentage = Column(Numeric, nullable=True, default=5.0)
    take_profit_percentage = Column(Numeric, nullable=True, default=10.0)
    strategy_config = Column(JSONB, nullable=True, default={}, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationship
    profile = relationship("Profile", back_populates="trading_settings")


# ============================================================================
# MARKET DATA MODELS
# ============================================================================

class MarketData(Base):
    """Real-time market data snapshots."""
    __tablename__ = "market_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    exchange = Column(Text, nullable=False)  # USER-DEFINED enum
    symbol = Column(Text, nullable=False)
    price = Column(Numeric, nullable=False)
    volume_24h = Column(Numeric, nullable=True)
    change_24h = Column(Numeric, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ============================================================================
# AI & SIGNALS MODELS
# ============================================================================

class AIInsight(Base):
    """AI-generated insights for users."""
    __tablename__ = "ai_insights"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    insight_type = Column(Text, nullable=False)  # opportunity, warning, strategy, market_analysis, risk_alert
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    confidence_score = Column(Integer, nullable=False)  # 0-100
    action_required = Column(Text, nullable=True)
    priority = Column(
        Text, 
        nullable=False, 
        default="medium",
        server_default="medium"
    )  # low, medium, high, critical
    related_symbols = Column(ARRAY(Text), nullable=True)
    metadata_payload = Column(JSONB, nullable=True, default={}, server_default="{}")
    is_read = Column(Boolean, nullable=False, default=False, server_default="false")
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationship
    profile = relationship("Profile", back_populates="ai_insights")


class TradingSignal(Base):
    """Trading signals from AI analysis."""
    __tablename__ = "trading_signals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    symbol = Column(Text, nullable=False)
    signal_type = Column(Text, nullable=False)  # buy, sell, hold
    strength = Column(Integer, nullable=False)  # 0-100
    price_target = Column(Numeric, nullable=True)
    stop_loss = Column(Numeric, nullable=True)
    take_profit = Column(Numeric, nullable=True)
    confidence_score = Column(Integer, nullable=False)  # 0-100
    ai_analysis = Column(Text, nullable=True)
    source = Column(Text, nullable=False, default="gemini_ai", server_default="gemini_ai")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MarketAlert(Base):
    """Price and market alerts for users."""
    __tablename__ = "market_alerts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    alert_type = Column(Text, nullable=False)  # price_target, volume_spike, trend_change, resistance_break, support_break
    symbol = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    trigger_price = Column(Numeric, nullable=True)
    current_price = Column(Numeric, nullable=True)
    target_price = Column(Numeric, nullable=True)
    percentage_change = Column(Numeric, nullable=True)
    is_triggered = Column(Boolean, nullable=False, default=False, server_default="false")
    is_read = Column(Boolean, nullable=False, default=False, server_default="false")
    priority = Column(
        Text, 
        nullable=False, 
        default="medium",
        server_default="medium"
    )  # low, medium, high
    metadata_payload = Column(JSONB, nullable=True, default={}, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationship
    profile = relationship("Profile", back_populates="market_alerts")


# ============================================================================
# NOTIFICATION & ACTIVITY MODELS
# ============================================================================

class Notification(Base):
    """User notifications."""
    __tablename__ = "notifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    title = Column(Text, nullable=False)
    message = Column(Text, nullable=False)
    type = Column(Text, nullable=False)  # success, info, warning, error
    is_read = Column(Boolean, nullable=False, default=False, server_default="false")
    action_url = Column(Text, nullable=True)
    metadata_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationship
    profile = relationship("Profile", back_populates="notifications")


class UserActivity(Base):
    """Public activity feed."""
    __tablename__ = "user_activities"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    activity_type = Column(Text, nullable=False)  # trade_profit, trade_loss, withdrawal, deposit, registration, milestone
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    amount = Column(Numeric, nullable=True)
    symbol = Column(Text, nullable=True)
    city = Column(Text, nullable=True)
    country = Column(Text, nullable=True, default="Poland", server_default="Poland")
    is_public = Column(Boolean, nullable=False, default=True, server_default="true")
    show_amount = Column(Boolean, nullable=True, default=False, server_default="false")
    show_location = Column(Boolean, nullable=True, default=False, server_default="false")
    metadata_payload = Column(JSONB, nullable=True, default={}, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationship
    profile = relationship("Profile", back_populates="user_activities")


# ============================================================================
# SUBSCRIPTION & BILLING MODELS
# ============================================================================

class SubscriptionHistory(Base):
    """Subscription change history."""
    __tablename__ = "subscription_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("public.profiles.user_id"), nullable=True)
    action = Column(Text, nullable=False)  # started, upgraded, downgraded, cancelled, reactivated
    from_tier = Column(Text, nullable=True)
    to_tier = Column(Text, nullable=True)
    stripe_event_id = Column(Text, nullable=True)
    metadata_payload = Column(JSONB, nullable=True, default={}, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())


class BotPerformanceStats(Base):
    """Aggregated bot performance statistics."""
    __tablename__ = "bot_performance_stats"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    period_type = Column(Text, nullable=False, unique=True)
    stats_data = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())


# ============================================================================
# RATE LIMITING MODEL
# ============================================================================

class RateLimitAttempt(Base):
    """Rate limiting tracking."""
    __tablename__ = "rate_limit_attempts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    identifier = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    metadata = Column(JSONB, nullable=True, default={}, server_default="{}")
