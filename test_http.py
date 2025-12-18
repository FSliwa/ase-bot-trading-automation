import sys
import os
from pathlib import Path

# Mimic run_test_mode.py setup
sys.path.append(str(Path(__file__).parent))
print(sys.path)

os.environ["SUPABASE_DB_URL"] = "sqlite:///:memory:"
os.environ["ALLOW_SQLITE_FALLBACK"] = "1"
os.environ["LOG_LEVEL"] = "INFO"
os.environ["EXCHANGE_NAME"] = "mock_exchange"

try:
    from bot.logging_setup import get_logger
    print("logging_setup imported")
    
    from bot.auto_trader import AutomatedTradingBot
    print("auto_trader imported")
    
    from bot.broker.enhanced_paper import EnhancedPaperBroker
    print("EnhancedPaperBroker imported")
    
    from bot.db import init_db
    print("init_db imported")
    
    # Try to initialize bot to trigger the lazy import
    bot = AutomatedTradingBot(test_mode=True)
    print("AutomatedTradingBot initialized")
    
    # Trigger AI init (which happens in initialize())
    import asyncio
    async def run_init():
        await bot.initialize()
    asyncio.run(run_init())
    print("AutomatedTradingBot.initialize() called")

except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")
