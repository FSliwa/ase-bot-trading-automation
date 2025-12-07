#!/usr/bin/env python3
"""
Direct launcher for the trading bot using hardcoded credentials found in the codebase.
Bypasses database connection issues by using local SQLite fallback.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM"
sys.path.insert(0, str(project_root))

# Set environment variables
os.environ["EXCHANGE_API_KEY"] = "Msr0cE4bwQNHQAip8utQ54D51EjuQTbH3NPyNLAZBoFDJ3FJgRNAYp1E9DbtXEla"
os.environ["EXCHANGE_API_SECRET"] = "rjrTCVMqRhauRcSErJUxoX9YdQwlzIlKHLslcLkxxeJeZtKO6E2YxzlR74JsnZmH"
os.environ["EXCHANGE_NAME"] = "binance"
os.environ["USE_TESTNET"] = "false"

# Force SQLite fallback to avoid network errors
os.environ["ALLOW_SQLITE_FALLBACK"] = "true"
os.environ["SUPABASE_DB_URL"] = "sqlite:///trading.db"
os.environ["DATABASE_URL"] = "sqlite:///trading.db"

# Disable AI analysis if keys are missing to prevent crash
if not os.getenv("CLAUDE_API_KEY"):
    print("⚠️  CLAUDE_API_KEY not found. AI analysis will be disabled.")

print("🚀 Launching bot with direct credentials...")
print(f"   Exchange: {os.environ['EXCHANGE_NAME']}")
print(f"   Testnet: {os.environ['USE_TESTNET']}")
print(f"   Database: {os.environ['DATABASE_URL']}")

try:
    from bot.auto_trader import main as run_bot
    asyncio.run(run_bot())
except KeyboardInterrupt:
    print("\n👋 Bot stopped by user")
except Exception as e:
    print(f"\n❌ Fatal error: {e}")
    import traceback
    traceback.print_exc()
