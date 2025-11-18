"""
Authentication API Routes for React Frontend
Provides JWT-based authentication endpoints matching frontend expectations
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import jwt
import bcrypt
import logging
import os
from typing import Optional
from bot.database import DatabaseManager
from bot.models import Profile

logger = logging.getLogger(__name__)

# Create router
auth_router = APIRouter(prefix="/api", tags=["Authentication"])

# Security
security = HTTPBearer()

# JWT Configuration from environment
JWT_SECRET = os.getenv("JWT_SECRET", "your-jwt-secret-key-here")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRES", "86400")) // 3600

# Pydantic Models
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    username: str  # Changed from email to match login logic
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime
    is_active: bool = True
    role: str = "user"

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_access_token(user_data: dict) -> str:
    """Create JWT access token"""
    to_encode = user_data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT token and return user data"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")


@auth_router.post("/auth/register")
async def register_user(user_data: UserRegister):
    """
    Register a new user in Supabase database
    
    - **username**: Unique username (3-50 characters)
    - **email**: Valid email address
    - **password**: Minimum 6 characters
    """
    try:
        # Validate input
        if len(user_data.username) < 3:
            raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
        if len(user_data.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        
        with DatabaseManager() as db:
            # Check if username already exists
            existing_user = db.session.query(Profile).filter(
                Profile.username == user_data.username
            ).first()
            if existing_user:
                raise HTTPException(status_code=400, detail="Username already registered")
            
            # Check if email already exists
            existing_email = db.session.query(Profile).filter(
                Profile.email == user_data.email
            ).first()
            if existing_email:
                raise HTTPException(status_code=400, detail="Email already registered")
            
            # Note: In production with Supabase Auth, user creation should go through
            # Supabase Auth API, not directly to the database. This is a simplified version.
            # TODO: Integrate with Supabase Auth API for proper user creation
            
            logger.info(f"Registration attempt for: {user_data.username}")
            
            return {
                "message": "User registration initiated. Please complete signup through Supabase Auth.",
                "user": {
                    "username": user_data.username,
                    "email": user_data.email
                },
                "note": "This endpoint should integrate with Supabase Auth API"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@auth_router.post("/auth/login")
async def login_user(credentials: UserLogin):
    """
    Authenticate user and return JWT token
    
    - **username**: User's username
    - **password**: User's password
    """
    try:
        with DatabaseManager() as db:
            # Find user by username
            profile = db.session.query(Profile).filter(
                Profile.username == credentials.username
            ).first()
            
            if not profile:
                raise HTTPException(status_code=401, detail="Invalid username or password")
            
            # Note: In production with Supabase Auth, password verification
            # should go through Supabase Auth API, not locally
            # TODO: Integrate with Supabase Auth API for proper authentication
            
            # Update last login timestamp
            profile.last_login_at = datetime.utcnow()
            db.session.commit()
            
            # Generate JWT token
            token_data = {
                "sub": str(profile.user_id),
                "username": profile.username,
                "exp": datetime.utcnow() + timedelta(hours=24)
            }
            token = jwt.encode(token_data, JWT_SECRET, algorithm=JWT_ALGORITHM)
            
            logger.info(f"User logged in: {profile.username}")
            
            return {
                "access_token": token,
                "token_type": "bearer",
                "expires_in": 86400,  # 24 hours in seconds
                "user": {
                    "id": str(profile.user_id),
                    "username": profile.username,
                    "email": profile.email,
                    "subscription_tier": profile.subscription_tier
                }
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@auth_router.get("/users/me", response_model=UserResponse)
async def get_current_user(token_data: dict = Depends(verify_token)):
    """Get current user information from Supabase"""
    try:
        user_id = token_data["sub"]  # UUID as string
        
        with DatabaseManager() as db:
            profile = db.session.query(Profile).filter(
                Profile.user_id == user_id
            ).first()
            
            if not profile:
                raise HTTPException(status_code=404, detail="User not found")
            
            return {
                "id": str(profile.user_id),
                "username": profile.username,
                "email": profile.email,
                "created_at": profile.created_at,
                "subscription_tier": profile.subscription_tier,
                "subscription_status": profile.subscription_status
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user")


@auth_router.put("/users/me", response_model=UserResponse)
async def update_current_user(
    user_update: dict,
    token_data: dict = Depends(verify_token)
):
    """Update current user information in Supabase"""
    try:
        user_id = token_data["sub"]  # UUID as string
        
        with DatabaseManager() as db:
            profile = db.session.query(Profile).filter(
                Profile.user_id == user_id
            ).first()
            
            if not profile:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Update allowed fields
            if "username" in user_update:
                # Check if username is already taken
                existing = db.session.query(Profile).filter(
                    Profile.username == user_update["username"],
                    Profile.user_id != user_id
                ).first()
                if existing:
                    raise HTTPException(status_code=400, detail="Username already taken")
                profile.username = user_update["username"]
            
            if "email" in user_update:
                # Check if email is already taken
                existing = db.session.query(Profile).filter(
                    Profile.email == user_update["email"],
                    Profile.user_id != user_id
                ).first()
                if existing:
                    raise HTTPException(status_code=400, detail="Email already registered")
                profile.email = user_update["email"]
            
            profile.updated_at = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"User updated: {profile.email}")
            
            return {
                "id": str(profile.user_id),
                "username": profile.username,
                "email": profile.email,
                "created_at": profile.created_at,
                "subscription_tier": profile.subscription_tier,
                "subscription_status": profile.subscription_status
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user")

@auth_router.post("/logout")
async def logout_user(token_data: dict = Depends(verify_token)):
    """Logout user (in a real app, you'd invalidate the token)"""
    try:
        user_id = token_data["sub"]
        logger.info(f"User logged out: {user_id}")
        
        # In a real application, you would:
        # 1. Add the token to a blacklist
        # 2. Store blacklisted tokens in Redis with expiration
        # 3. Check blacklist in verify_token function
        
        return {"message": "Successfully logged out"}
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")

# Health check for auth service
@auth_router.get("/auth/health")
async def auth_health_check():
    """Health check for authentication service"""
    try:
        with DatabaseManager() as db:
            profile_count = db.session.query(Profile).count()
            
        return {
            "service": "authentication",
            "status": "healthy",
            "timestamp": datetime.utcnow(),
            "registered_users": profile_count,
            "version": "2.0.0",
            "database": "supabase_postgresql"
        }
    except Exception as e:
        logger.error(f"Auth health check failed: {e}")
        return {
            "service": "authentication",
            "status": "degraded",
            "timestamp": datetime.utcnow(),
            "error": str(e),
            "version": "1.0.0"
        }

# Get authentication statistics (admin endpoint)
@auth_router.get("/auth/stats")
async def get_auth_stats():
    """Get authentication statistics from Supabase"""
    try:
        with DatabaseManager() as db:
            total_users = db.session.query(Profile).count()
            active_subs = db.session.query(Profile).filter(
                Profile.subscription_status == 'active'
            ).count()
            
            # Get recent registrations (last 7 days)
            week_ago = datetime.utcnow() - timedelta(days=7)
            recent_registrations = db.session.query(Profile).filter(
                Profile.created_at >= week_ago
            ).count()
            
            # Subscription tier breakdown
            free_users = db.session.query(Profile).filter(
                Profile.subscription_tier == 'free'
            ).count()
            pro_users = db.session.query(Profile).filter(
                Profile.subscription_tier == 'pro'
            ).count()
            
            return {
                "total_users": total_users,
                "active_subscriptions": active_subs,
                "recent_registrations": recent_registrations,
                "free_tier": free_users,
                "pro_tier": pro_users,
                "timestamp": datetime.utcnow()
            }
            
    except Exception as e:
        logger.error(f"Auth stats error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")
