"""
Database initialization script for VPS features
Creates all necessary tables for user management, sessions, and API keys.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from bot.user_manager import Base, User, UserSession, UserApiKey
from bot.db import engine, SessionLocal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_database():
    """Initialize database with all required tables"""
    try:
        logger.info("Creating database tables...")
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        
        logger.info("✅ Database tables created successfully")
        
        # Test database connection
        with SessionLocal() as db:
            # Check if tables exist
            from sqlalchemy import text
            tables = db.execute(text("SELECT name FROM sqlite_master WHERE type='table';")).fetchall()
            table_names = [table[0] for table in tables]
            
            logger.info(f"📋 Created tables: {', '.join(table_names)}")
            
            required_tables = ['users', 'user_sessions', 'user_api_keys']
            missing_tables = [table for table in required_tables if table not in table_names]
            
            if missing_tables:
                logger.warning(f"⚠️  Missing tables: {', '.join(missing_tables)}")
            else:
                logger.info("✅ All required tables present")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False

def create_demo_user():
    """Create a demo user for testing"""
    try:
        from bot.user_manager import get_user_manager, UserPlan
        
        user_manager = get_user_manager()
        
        demo_user = user_manager.create_user(
            email="demo@tradingbot.com",
            username="demo",
            password="demo123",
            plan=UserPlan.PRO
        )
        
        logger.info(f"✅ Demo user created: {demo_user['email']}")
        return demo_user
        
    except Exception as e:
        if "already exists" in str(e):
            logger.info("ℹ️  Demo user already exists")
        else:
            logger.error(f"❌ Failed to create demo user: {e}")
        return None

if __name__ == "__main__":
    print("🚀 Initializing VPS Trading Bot Database...")
    
    # Initialize database
    if init_database():
        print("✅ Database initialized successfully")
        
        # Create demo user
        demo_user = create_demo_user()
        
        print("\n🎉 Database setup complete!")
        print("\n📋 Next steps:")
        print("1. Start the server: python -m uvicorn web.app:app --host 0.0.0.0 --port 8010")
        print("2. Test user registration: curl -X POST http://localhost:8010/api/auth/register ...")
        print("3. Access dashboard: http://localhost:8010")
        
        if demo_user:
            print(f"\n🎭 Demo user credentials:")
            print(f"   Email: demo@tradingbot.com")
            print(f"   Password: demo123")
            print(f"   Plan: PRO")
    else:
        print("❌ Database initialization failed")
        sys.exit(1)
