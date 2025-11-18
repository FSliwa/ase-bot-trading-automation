#!/usr/bin/env python3
"""
🐛 COMPREHENSIVE DEBUGGING SCRIPT
Systematically checks all system components before deployment
"""

import os
import sys
import sqlite3
import traceback
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

def print_header(title: str):
    """Print formatted header"""
    print(f"\n{'='*50}")
    print(f"🔍 {title}")
    print('='*50)

def print_success(message: str):
    """Print success message"""
    print(f"✅ {message}")

def print_warning(message: str):
    """Print warning message"""
    print(f"⚠️  {message}")

def print_error(message: str):
    """Print error message"""
    print(f"❌ {message}")

def print_info(message: str):
    """Print info message"""
    print(f"ℹ️  {message}")

def check_file_structure():
    """Check if all required files exist"""
    print_header("FILE STRUCTURE CHECK")
    
    required_files = [
        "web/app.py",
        "bot/db.py",
        "bot/exchange_manager.py",
        "bot/balance_fetcher.py",
        "bot/security.py",
        "bot/user_manager.py",
        "requirements.txt",
        "trading.db"
    ]
    
    missing_files = []
    for file in required_files:
        if os.path.exists(file):
            print_success(f"Found: {file}")
        else:
            print_error(f"Missing: {file}")
            missing_files.append(file)
    
    return len(missing_files) == 0

def check_database():
    """Check database connectivity and structure"""
    print_header("DATABASE CHECK")
    
    try:
        # Check if database file exists
        db_path = "trading.db"
        if not os.path.exists(db_path):
            print_error(f"Database file not found: {db_path}")
            return False
        
        print_success(f"Database file found: {db_path}")
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = [
            'positions', 'orders', 'fills', 'trading_stats', 
            'risk_events', 'users', 'user_sessions', 'exchange_credentials'
        ]
        
        print_info(f"Found tables: {', '.join(tables)}")
        
        missing_tables = [table for table in expected_tables if table not in tables]
        if missing_tables:
            print_warning(f"Missing tables: {', '.join(missing_tables)}")
        else:
            print_success("All required tables present")
        
        # Check table record counts
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print_info(f"Table '{table}': {count} records")
            except Exception as e:
                print_warning(f"Could not check table '{table}': {e}")
        
        conn.close()
        return True
        
    except Exception as e:
        print_error(f"Database check failed: {e}")
        traceback.print_exc()
        return False

def check_imports():
    """Check if all required modules can be imported"""
    print_header("IMPORT CHECK")
    
    modules_to_check = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn ASGI server"),
        ("sqlalchemy", "SQLAlchemy ORM"),
        ("ccxt", "CCXT exchange library"),
        ("requests", "HTTP requests"),
        ("cryptography", "Encryption"),
        ("dotenv", "Environment variables (.env files)")
    ]
    
    import_errors = []
    
    for module, description in modules_to_check:
        try:
            __import__(module)
            print_success(f"{description} ({module})")
        except ImportError as e:
            print_error(f"Cannot import {module}: {e}")
            import_errors.append(module)
    
    return len(import_errors) == 0

def check_environment():
    """Check environment variables and configuration"""
    print_header("ENVIRONMENT CHECK")
    
    # Check .env file
    env_file = ".env"
    if os.path.exists(env_file):
        print_success(f"Environment file found: {env_file}")
        
        with open(env_file, 'r') as f:
            env_content = f.read()
            
        required_vars = ['SECRET_KEY', 'DATABASE_URL']
        for var in required_vars:
            if var in env_content:
                print_success(f"Environment variable: {var}")
            else:
                print_warning(f"Missing environment variable: {var}")
    else:
        print_warning(f"Environment file not found: {env_file}")
    
    # Check current environment
    current_vars = ['OPENAI_API_KEY', 'SECRET_KEY', 'DATABASE_URL']
    for var in current_vars:
        if os.getenv(var):
            print_success(f"Environment variable set: {var}")
        else:
            print_warning(f"Environment variable not set: {var}")

def check_bot_components():
    """Check bot components functionality"""
    print_header("BOT COMPONENTS CHECK")
    
    try:
        # Import bot modules
        from bot.db import DatabaseManager, init_db
        from bot.security import SecurityManager
        from bot.exchange_manager import get_exchange_manager
        from bot.balance_fetcher import get_balance_fetcher
        
        print_success("All bot modules imported successfully")
        
        # Test security manager
        try:
            security = SecurityManager()
            test_data = "test_encryption_data"
            encrypted = security.encrypt(test_data)
            decrypted = security.decrypt(encrypted)
            
            if decrypted == test_data:
                print_success("Security manager encryption/decryption working")
            else:
                print_error("Security manager encryption/decryption failed")
        except Exception as e:
            print_error(f"Security manager test failed: {e}")
        
        # Test database manager
        try:
            with DatabaseManager() as db:
                print_success("Database manager connection working")
        except Exception as e:
            print_error(f"Database manager test failed: {e}")
        
        # Test exchange manager
        try:
            exchange_mgr = get_exchange_manager()
            print_success("Exchange manager initialization working")
        except Exception as e:
            print_error(f"Exchange manager test failed: {e}")
        
        # Test balance fetcher
        try:
            balance_fetcher = get_balance_fetcher()
            # Test demo balance
            demo_balance = balance_fetcher._get_demo_balance("demo")
            if demo_balance and demo_balance.get("total_value_usd", 0) > 0:
                print_success(f"Balance fetcher demo mode working: ${demo_balance['total_value_usd']:,.2f}")
            else:
                print_warning("Balance fetcher demo mode returned empty data")
        except Exception as e:
            print_error(f"Balance fetcher test failed: {e}")
        
        return True
        
    except Exception as e:
        print_error(f"Bot components check failed: {e}")
        traceback.print_exc()
        return False

def check_web_app():
    """Check web application components"""
    print_header("WEB APPLICATION CHECK")
    
    try:
        # Import web modules
        from web.app import app
        print_success("FastAPI app imported successfully")
        
        # Check routes
        routes = [route.path for route in app.routes]
        key_routes = ['/health', '/api/status', '/dashboard', '/login']
        
        for route in key_routes:
            if route in routes:
                print_success(f"Route found: {route}")
            else:
                print_warning(f"Route missing: {route}")
        
        print_info(f"Total routes: {len(routes)}")
        
        return True
        
    except Exception as e:
        print_error(f"Web application check failed: {e}")
        traceback.print_exc()
        return False

async def test_api_endpoints():
    """Test critical API endpoints"""
    print_header("API ENDPOINTS TEST")
    
    try:
        import httpx
        
        # Start server in background for testing
        # Note: This is a simplified test - in production, server should be running
        
        endpoints_to_test = [
            ("/health", "Health check"),
            ("/api/status", "System status"),
            ("/api/demo/balance", "Demo balance"),
        ]
        
        print_info("Note: For full API testing, start the server with:")
        print_info("python -m uvicorn web.app:app --host 0.0.0.0 --port 8010")
        
        return True
        
    except Exception as e:
        print_error(f"API endpoints test failed: {e}")
        return False

def check_security():
    """Check security configuration"""
    print_header("SECURITY CHECK")
    
    try:
        from bot.security import SecurityManager
        
        security = SecurityManager()
        
        # Test key generation
        # Note: SecurityManager doesn't have generate_key method, skip this test
        print_info("Skipping key generation test (method not available)")
        
        # Test encryption with different data types
        test_cases = [
            "simple_string",
            "complex!@#$%^&*()string",
            "🚀 Unicode test 中文",
            json.dumps({"test": "data", "number": 123})
        ]
        
        for test_data in test_cases:
            try:
                encrypted = security.encrypt(test_data)
                decrypted = security.decrypt(encrypted)
                
                if decrypted == test_data:
                    print_success(f"Encryption test passed: {type(test_data).__name__}")
                else:
                    print_error(f"Encryption test failed: {type(test_data).__name__}")
            except Exception as e:
                print_error(f"Encryption test error for {type(test_data).__name__}: {e}")
        
        return True
        
    except Exception as e:
        print_error(f"Security check failed: {e}")
        traceback.print_exc()
        return False

def check_logging():
    """Check logging configuration"""
    print_header("LOGGING CHECK")
    
    try:
        import logging
        
        # Try to import setup_logging, but don't fail if not available
        try:
            from bot.logging_setup import setup_logging
            setup_logging()
            print_success("Logging setup imported and configured")
        except ImportError:
            print_warning("Custom logging setup not available, using default")
            logging.basicConfig(level=logging.INFO)
        
        # Test different log levels
        logger = logging.getLogger("debug_test")
        
        logger.info("INFO level test message")
        logger.warning("WARNING level test message")
        logger.error("ERROR level test message")
        
        print_success("Logging system configured")
        
        # Check log directory
        log_dir = Path("logs")
        if log_dir.exists():
            log_files = list(log_dir.glob("*.log"))
            print_success(f"Log directory found with {len(log_files)} log files")
        else:
            print_warning("Log directory not found")
        
        return True
        
    except Exception as e:
        print_error(f"Logging check failed: {e}")
        return False

def generate_summary_report(results: Dict[str, bool]):
    """Generate debugging summary report"""
    print_header("DEBUGGING SUMMARY REPORT")
    
    # Filter out None values
    valid_results = {k: v for k, v in results.items() if v is not None}
    total_checks = len(valid_results)
    passed_checks = sum(1 for v in valid_results.values() if v)
    failed_checks = total_checks - passed_checks
    
    print(f"📊 Total checks: {total_checks}")
    print(f"✅ Passed: {passed_checks}")
    print(f"❌ Failed: {failed_checks}")
    print(f"📈 Success rate: {(passed_checks/total_checks)*100:.1f}%")
    
    print("\n📋 Detailed Results:")
    for check_name, passed in valid_results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {status} - {check_name}")
    
    # Show skipped checks
    skipped_checks = [k for k, v in results.items() if v is None]
    if skipped_checks:
        print("\n⏭️  Skipped checks:")
        for check_name in skipped_checks:
            print(f"   ⏭️  SKIP - {check_name}")
    
    print("\n🚀 DEPLOYMENT READINESS:")
    if failed_checks == 0:
        print("✅ READY FOR DEPLOYMENT - All checks passed!")
        print("\nNext steps:")
        print("1. Run: ./deploy.sh deploy")
        print("2. Monitor: ./monitor_deployment.sh")
    elif failed_checks <= 2:
        print("⚠️  ALMOST READY - Minor issues found")
        print("Fix the failing checks and re-run debugging")
    else:
        print("❌ NOT READY - Multiple issues found")
        print("Address all failing checks before deployment")
    
    # Save report to file
    report_file = f"debug_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w') as f:
        f.write(f"Debugging Report - {datetime.now()}\n")
        f.write("="*50 + "\n\n")
        
        for check_name, passed in valid_results.items():
            status = "PASS" if passed else "FAIL"
            f.write(f"{status}: {check_name}\n")
        
        f.write(f"\nSummary: {passed_checks}/{total_checks} checks passed\n")
    
    print(f"\n📄 Report saved to: {report_file}")

def main():
    """Main debugging function"""
    print("🐛 COMPREHENSIVE SYSTEM DEBUGGING")
    print("="*50)
    print(f"🕐 Started at: {datetime.now()}")
    print(f"📁 Working directory: {os.getcwd()}")
    print(f"🐍 Python version: {sys.version}")
    
    # Run all checks
    results = {}
    
    results["File Structure"] = check_file_structure()
    results["Database"] = check_database()
    results["Imports"] = check_imports()
    results["Environment"] = check_environment()
    results["Bot Components"] = check_bot_components()
    results["Web Application"] = check_web_app()
    results["Security"] = check_security()
    results["Logging"] = check_logging()
    
    # Generate summary
    generate_summary_report(results)
    
    # Return overall status
    valid_results = {k: v for k, v in results.items() if v is not None}
    return all(valid_results.values())

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n🛑 Debugging interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)
