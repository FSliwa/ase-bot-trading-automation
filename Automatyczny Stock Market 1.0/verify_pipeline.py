import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

# Add project root to path
sys.path.append(str(Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM"))

# Mock aiohttp if not present
try:
    import aiohttp
except ImportError:
    sys.modules["aiohttp"] = MagicMock()

# Set dummy env vars to avoid DB init error
os.environ["SUPABASE_DB_URL"] = "sqlite:///:memory:"
os.environ["ALLOW_SQLITE_FALLBACK"] = "1"

from bot.services.market_analysis_service import MarketAnalysisService
from bot.db import DatabaseManager, Trade, TradingSignal

async def verify_pipeline():
    print("🚀 Starting Pipeline Verification...")
    
    # Mock DB Manager
    db_manager = MagicMock(spec=DatabaseManager)
    session_mock = MagicMock()
    db_manager.__enter__.return_value = session_mock
    
    # Mock Trades and Signals
    mock_trade = MagicMock()
    mock_trade.symbol = "BTC/USDT"
    mock_trade.trade_type = "BUY"
    mock_trade.price = 50000.0
    mock_trade.amount = 0.1
    mock_trade.pnl = 100.0
    mock_trade.created_at = datetime.now()
    mock_trade.source = "bot"
    mock_trade.emotion = "neutral"
    
    mock_signal = MagicMock()
    mock_signal.symbol = "BTC/USDT"
    mock_signal.signal_type = "BUY"
    mock_signal.strength = "strong"
    mock_signal.confidence_score = 85.0
    mock_signal.price_target = 55000.0
    mock_signal.created_at = datetime.now()
    mock_signal.ai_analysis = "Bullish trend"
    mock_signal.source = "ai"
    
    # Setup DB query results
    session_mock.session.execute.return_value.scalars.return_value.all.side_effect = [
        [mock_trade], # Trades
        [mock_signal] # Signals
    ]
    
    # Mock Analyzer
    analyzer = MagicMock()
    analyzer.claude_client.messages.create = AsyncMock()
    analyzer.claude_model = "claude-3-opus-latest"
    analyzer.claude_max_tokens = 4096
    analyzer.claude_temperature = 0.2
    
    # Mock AI Response
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"action": "BUY", "confidence": 85, "reasoning": "Test reasoning"}')]
    analyzer.claude_client.messages.create.return_value = mock_response
    analyzer._extract_json.return_value = {"action": "BUY", "confidence": 85, "reasoning": "Test reasoning"}
    
    # Initialize Service
    service = MarketAnalysisService(db_manager, analyzer)
    
    # Mock External APIs
    service.fetch_crypto_tweets = AsyncMock(return_value=[
        {"text": "Bitcoin is going up!", "author": "user1", "likes": 100, "retweets": 50}
    ])
    service.fetch_crypto_news = AsyncMock(return_value=[
        "[2023-10-27] Bitcoin hits new high: Details here"
    ])
    
    # Run Generation
    market_data = {
        "current_price": 50000.0,
        "change_24h_percent": 5.0,
        "volume_24h": 1000000,
        "high_24h": 51000.0,
        "low_24h": 49000.0
    }
    
    print("\n📊 Generating Signal for BTC...")
    result = await service.generate_signal("BTC", market_data)
    
    if result:
        print(f"✅ Signal Generated: {result}")
        # Note: In the real bot, auto_trader calls save_trading_signal.
        # Here we are just testing the service generation.
        # But we can verify the service output structure matches what save_trading_signal expects.
        
        assert "action" in result
        assert "confidence" in result
        assert "reasoning" in result
        
        print("✅ Pipeline Verification Successful!")
    else:
        print("❌ Signal Generation Failed")

if __name__ == "__main__":
    asyncio.run(verify_pipeline())
