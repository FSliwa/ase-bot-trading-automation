#!/usr/bin/env python3
"""
Initialize the database with all tables including the new ExchangeCredential table.
Run this script after adding new OAuth/API functionality.
"""

import sys
from pathlib import Path

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent))

from bot.db import init_db, Base, engine
from bot.security import get_security_manager
import os

def main():
    """Initialize database and create all tables."""
    print("🔧 Initializing Trading Bot Database...")
    
    # Ensure encryption key is set up
    encryption_key = os.getenv("ENCRYPTION_KEY")
    if not encryption_key:
        print("⚠️  ENCRYPTION_KEY not found in environment variables.")
        print("   Generating a new key for this session...")
        from cryptography.fernet import Fernet
        new_key = Fernet.generate_key()
        print(f"   Please add this to your .env file:")
        print(f"   ENCRYPTION_KEY={new_key.decode()}")
        print()
        
        # Set temporarily for this session
        os.environ["ENCRYPTION_KEY"] = new_key.decode()
    
    # Create all tables
    try:
        init_db()
        print("✅ Database initialized successfully!")
        print("   📊 Created/verified tables:")
        
        # List all tables
        for table_name in Base.metadata.tables.keys():
            print(f"      - {table_name}")
        
        print()
        print("🔐 Exchange Credential Management:")
        print("   - OAuth tokens and API keys are encrypted")
        print("   - User session management ready")
        print("   - Exchange connections can be managed via /exchanges")
        
        print()
        print("🚀 You can now:")
        print("   1. Start the application: python start_app.py")
        print("   2. Visit http://localhost:8008/exchanges to manage connections")
        print("   3. Connect exchanges via OAuth or API keys")
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
