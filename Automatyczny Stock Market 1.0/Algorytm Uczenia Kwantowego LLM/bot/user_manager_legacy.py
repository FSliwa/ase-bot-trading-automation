"""
User Management System for Multi-Tenant Trading Bot
Handles user authentication, permissions, and account management for VPS deployment.
"""

import hashlib
import secrets
import jwt
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import logging
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

from bot.db import SessionLocal
from bot.security import get_security_manager

logger = logging.getLogger(__name__)

Base = declarative_base()

class UserPlan(str, Enum):
    """User subscription plans"""
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class UserStatus(str, Enum):
    """User account status"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"
    BANNED = "banned"

class User(Base):
    """User database model"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(255), nullable=False)
    
    # Account details
    plan = Column(SQLEnum(UserPlan), default=UserPlan.FREE)
    status = Column(SQLEnum(UserStatus), default=UserStatus.ACTIVE)
    
    # Limits based on plan
    max_positions = Column(Integer, default=3)
    max_api_calls_per_hour = Column(Integer, default=100)
    max_exchanges = Column(Integer, default=1)
    
    # Tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    last_activity = Column(DateTime)
    login_attempts = Column(Integer, default=0)
    
    # Settings
    timezone = Column(String(50), default="UTC")
    language = Column(String(10), default="en")
    email_notifications = Column(Boolean, default=True)
    push_notifications = Column(Boolean, default=True)

class UserSession(Base):
    """User session tracking"""
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    session_token = Column(String(255), unique=True, nullable=False)
    jwt_token = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_used = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    is_active = Column(Boolean, default=True)

class UserApiKey(Base):
    """User API keys for external access"""
    __tablename__ = "user_api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    key_name = Column(String(100), nullable=False)
    api_key = Column(String(255), unique=True, nullable=False)
    api_secret_hash = Column(String(255), nullable=False)
    permissions = Column(Text)  # JSON string of permissions
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    rate_limit_per_hour = Column(Integer, default=100)

class UserManager:
    """Comprehensive user management system"""
    
    def __init__(self):
        self.security = get_security_manager()
        self.jwt_secret = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
        self.session_timeout = int(os.getenv("SESSION_TIMEOUT_HOURS", "24"))
        
        # Plan limits configuration
        self.plan_limits = {
            UserPlan.FREE: {
                "max_positions": 3,
                "max_api_calls_per_hour": 100,
                "max_exchanges": 1,
                "max_trading_volume": 1000.0,
                "features": ["basic_trading", "demo_mode"]
            },
            UserPlan.BASIC: {
                "max_positions": 10,
                "max_api_calls_per_hour": 500,
                "max_exchanges": 2,
                "max_trading_volume": 10000.0,
                "features": ["basic_trading", "demo_mode", "live_trading", "basic_analytics"]
            },
            UserPlan.PRO: {
                "max_positions": 50,
                "max_api_calls_per_hour": 2000,
                "max_exchanges": 5,
                "max_trading_volume": 100000.0,
                "features": ["basic_trading", "demo_mode", "live_trading", "advanced_analytics", "ai_signals", "portfolio_management"]
            },
            UserPlan.ENTERPRISE: {
                "max_positions": 999,
                "max_api_calls_per_hour": 10000,
                "max_exchanges": 10,
                "max_trading_volume": 1000000.0,
                "features": ["all_features", "priority_support", "custom_strategies", "api_access"]
            }
        }
    
    def create_user(self, email: str, username: str, password: str, plan: UserPlan = UserPlan.FREE) -> Dict[str, Any]:
        """Create a new user account"""
        try:
            with SessionLocal() as db:
                # Check if user already exists
                existing_user = db.query(User).filter(
                    (User.email == email) | (User.username == username)
                ).first()
                
                if existing_user:
                    raise ValueError("User with this email or username already exists")
                
                # Generate salt and hash password
                salt = secrets.token_hex(32)
                password_hash = self._hash_password(password, salt)
                
                # Get plan limits
                limits = self.plan_limits[plan]
                
                # Create user
                user = User(
                    email=email,
                    username=username,
                    password_hash=password_hash,
                    salt=salt,
                    plan=plan,
                    max_positions=limits["max_positions"],
                    max_api_calls_per_hour=limits["max_api_calls_per_hour"],
                    max_exchanges=limits["max_exchanges"]
                )
                
                db.add(user)
                db.commit()
                db.refresh(user)
                
                logger.info(f"Created user: {email} with plan: {plan}")
                
                return {
                    "user_id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "plan": user.plan,
                    "status": user.status,
                    "created_at": user.created_at.isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise
    
    def authenticate_user(self, email: str, password: str, ip_address: str = None, user_agent: str = None) -> Dict[str, Any]:
        """Authenticate user and create session"""
        try:
            with SessionLocal() as db:
                user = db.query(User).filter(User.email == email).first()
                
                if not user:
                    raise ValueError("Invalid credentials")
                
                if user.status != UserStatus.ACTIVE:
                    raise ValueError(f"Account is {user.status}")
                
                # Check password
                if not self._verify_password(password, user.password_hash, user.salt):
                    # Increment failed attempts
                    user.login_attempts += 1
                    if user.login_attempts >= 5:
                        user.status = UserStatus.SUSPENDED
                        logger.warning(f"User {email} suspended due to too many failed login attempts")
                    db.commit()
                    raise ValueError("Invalid credentials")
                
                # Reset failed attempts on successful login
                user.login_attempts = 0
                user.last_login = datetime.utcnow()
                user.last_activity = datetime.utcnow()
                
                # Create JWT token
                jwt_payload = {
                    "user_id": user.id,
                    "email": user.email,
                    "plan": user.plan,
                    "exp": datetime.utcnow() + timedelta(hours=self.session_timeout),
                    "iat": datetime.utcnow()
                }
                
                jwt_token = jwt.encode(jwt_payload, self.jwt_secret, algorithm="HS256")
                session_token = secrets.token_urlsafe(32)
                
                # Create session record
                session = UserSession(
                    user_id=user.id,
                    session_token=session_token,
                    jwt_token=jwt_token,
                    expires_at=datetime.utcnow() + timedelta(hours=self.session_timeout),
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                
                db.add(session)
                db.commit()
                
                logger.info(f"User {email} authenticated successfully")
                
                return {
                    "user_id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "plan": user.plan,
                    "jwt_token": jwt_token,
                    "session_token": session_token,
                    "expires_at": session.expires_at.isoformat(),
                    "permissions": self.get_user_permissions(user.id)
                }
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise
    
    def validate_jwt_token(self, token: str) -> Dict[str, Any]:
        """Validate JWT token and return user info"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            
            with SessionLocal() as db:
                user = db.query(User).filter(User.id == payload["user_id"]).first()
                
                if not user or user.status != UserStatus.ACTIVE:
                    raise ValueError("Invalid or inactive user")
                
                # Update last activity
                user.last_activity = datetime.utcnow()
                db.commit()
                
                return {
                    "user_id": user.id,
                    "email": user.email,
                    "plan": user.plan,
                    "valid": True
                }
                
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise
    
    def get_user_permissions(self, user_id: int) -> Dict[str, Any]:
        """Get user permissions based on plan"""
        try:
            with SessionLocal() as db:
                user = db.query(User).filter(User.id == user_id).first()
                
                if not user:
                    raise ValueError("User not found")
                
                plan_config = self.plan_limits[user.plan]
                
                return {
                    "plan": user.plan,
                    "limits": {
                        "max_positions": user.max_positions,
                        "max_api_calls_per_hour": user.max_api_calls_per_hour,
                        "max_exchanges": user.max_exchanges,
                        "max_trading_volume": plan_config["max_trading_volume"]
                    },
                    "features": plan_config["features"],
                    "status": user.status
                }
                
        except Exception as e:
            logger.error(f"Error getting user permissions: {e}")
            raise
    
    def get_user_limits(self, user_id: int) -> Dict[str, Any]:
        """Get user's current usage limits"""
        try:
            with SessionLocal() as db:
                user = db.query(User).filter(User.id == user_id).first()
                
                if not user:
                    raise ValueError("User not found")
                
                # TODO: Get current usage from other services
                current_usage = {
                    "positions": 0,  # Get from trading engine
                    "api_calls_today": 0,  # Get from rate limiter
                    "exchanges_connected": 0,  # Get from exchange manager
                    "trading_volume_24h": 0.0  # Get from trading history
                }
                
                plan_config = self.plan_limits[user.plan]
                
                return {
                    "limits": {
                        "max_positions": user.max_positions,
                        "max_api_calls_per_hour": user.max_api_calls_per_hour,
                        "max_exchanges": user.max_exchanges,
                        "max_trading_volume": plan_config["max_trading_volume"]
                    },
                    "current_usage": current_usage,
                    "remaining": {
                        "positions": user.max_positions - current_usage["positions"],
                        "api_calls": user.max_api_calls_per_hour - current_usage["api_calls_today"],
                        "exchanges": user.max_exchanges - current_usage["exchanges_connected"],
                        "trading_volume": plan_config["max_trading_volume"] - current_usage["trading_volume_24h"]
                    }
                }
                
        except Exception as e:
            logger.error(f"Error getting user limits: {e}")
            raise
    
    def upgrade_user_plan(self, user_id: int, new_plan: UserPlan) -> Dict[str, Any]:
        """Upgrade user's subscription plan"""
        try:
            with SessionLocal() as db:
                user = db.query(User).filter(User.id == user_id).first()
                
                if not user:
                    raise ValueError("User not found")
                
                old_plan = user.plan
                limits = self.plan_limits[new_plan]
                
                # Update user plan and limits
                user.plan = new_plan
                user.max_positions = limits["max_positions"]
                user.max_api_calls_per_hour = limits["max_api_calls_per_hour"]
                user.max_exchanges = limits["max_exchanges"]
                
                db.commit()
                
                logger.info(f"User {user.email} upgraded from {old_plan} to {new_plan}")
                
                return {
                    "user_id": user_id,
                    "old_plan": old_plan,
                    "new_plan": new_plan,
                    "new_limits": limits,
                    "upgraded_at": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error upgrading user plan: {e}")
            raise
    
    def create_api_key(self, user_id: int, key_name: str, permissions: List[str] = None) -> Dict[str, Any]:
        """Create API key for user"""
        try:
            with SessionLocal() as db:
                user = db.query(User).filter(User.id == user_id).first()
                
                if not user:
                    raise ValueError("User not found")
                
                # Check if user can create API keys
                plan_features = self.plan_limits[user.plan]["features"]
                if "api_access" not in plan_features:
                    raise ValueError("API access not available in your plan")
                
                # Generate API key and secret
                api_key = f"tb_{secrets.token_urlsafe(24)}"
                api_secret = secrets.token_urlsafe(32)
                api_secret_hash = self._hash_password(api_secret, user.salt)
                
                # Default permissions
                if permissions is None:
                    permissions = ["read_account", "read_positions"]
                
                # Create API key record
                api_key_record = UserApiKey(
                    user_id=user_id,
                    key_name=key_name,
                    api_key=api_key,
                    api_secret_hash=api_secret_hash,
                    permissions=",".join(permissions),
                    rate_limit_per_hour=user.max_api_calls_per_hour
                )
                
                db.add(api_key_record)
                db.commit()
                
                logger.info(f"Created API key for user {user.email}: {key_name}")
                
                return {
                    "api_key": api_key,
                    "api_secret": api_secret,  # Only returned once!
                    "key_name": key_name,
                    "permissions": permissions,
                    "created_at": api_key_record.created_at.isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error creating API key: {e}")
            raise
    
    def get_user_activity(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get user activity statistics"""
        try:
            with SessionLocal() as db:
                user = db.query(User).filter(User.id == user_id).first()
                
                if not user:
                    raise ValueError("User not found")
                
                # Calculate date range
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=days)
                
                # Get session activity
                sessions = db.query(UserSession).filter(
                    UserSession.user_id == user_id,
                    UserSession.created_at >= start_date
                ).all()
                
                return {
                    "user_id": user_id,
                    "period_days": days,
                    "total_sessions": len(sessions),
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                    "last_activity": user.last_activity.isoformat() if user.last_activity else None,
                    "account_created": user.created_at.isoformat(),
                    "current_plan": user.plan,
                    "status": user.status
                }
                
        except Exception as e:
            logger.error(f"Error getting user activity: {e}")
            raise
    
    def _hash_password(self, password: str, salt: str) -> str:
        """Hash password with salt"""
        return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
    
    def _verify_password(self, password: str, password_hash: str, salt: str) -> bool:
        """Verify password against hash"""
        return self._hash_password(password, salt) == password_hash


# Global instance
_user_manager: Optional[UserManager] = None

def get_user_manager() -> UserManager:
    """Get or create global UserManager instance"""
    global _user_manager
    
    if _user_manager is None:
        _user_manager = UserManager()
    
    return _user_manager
