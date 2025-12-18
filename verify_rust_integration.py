import asyncio
import logging
import sys
from unittest.mock import MagicMock

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Mock dependencies
sys.modules['bot.db'] = MagicMock()
sys.modules['bot.ai_analysis'] = MagicMock()
sys.modules['bot.tavily_web_search'] = MagicMock()

from bot.services.market_analysis_service import MarketAnalysisService

async def main():
    print("🚀 Starting Rust Integration Verification...")
    
    # Mock DB and Analyzer
    db_mock = MagicMock()
    analyzer_mock = MagicMock()
    
    service = MarketAnalysisService(db_mock, analyzer_mock)
    
    # Test symbol
    symbol = "BTC"
    market_data = {"current_price": 90000.0}
    
    print(f"📡 Requesting signal for {symbol}...")
    signal = await service.generate_signal(symbol, market_data)
    
    if signal:
        print(f"✅ Signal Received:\n{signal}")
    else:
        print("❌ No signal received (or Rust execution failed)")

if __name__ == "__main__":
    asyncio.run(main())
