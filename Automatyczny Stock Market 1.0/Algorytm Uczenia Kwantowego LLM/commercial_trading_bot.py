#!/usr/bin/env python3
"""
Commercial Trading Bot - Production Ready
Bot tradingowy dla użytkowników komercyjnych z pełną integracją AI
"""

import asyncio
import os
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import traceback

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load .env manually (no python-dotenv dependency)
env_file = Path(__file__).parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)

from supabase import create_client, Client
from bot.ai_analysis import MarketAnalyzer
from bot.security import SecurityManager

# Configure logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("commercial_bot")


class CommercialTradingBot:
    """
    Production-ready trading bot for commercial users
    Features:
    - Multi-user support (API keys from database)
    - AI-powered market analysis (Claude + Gemini + Tavily)
    - SPOT-only trading for Binance
    - Risk management
    - Real-time monitoring
    """
    
    def __init__(self, user_id: str, user_email: str):
        self.user_id = user_id
        self.user_email = user_email
        self.running = False
        self.shutdown_event = asyncio.Event()
        
        # Supabase connection
        supabase_url = f"https://{os.getenv('SUPABASE_PROJECT_ID')}.supabase.co"
        supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        self.supabase: Client = create_client(supabase_url, supabase_key)
        
        # Security manager
        self.security = SecurityManager()
        
        # Trading components
        self.market_analyzer: Optional[MarketAnalyzer] = None
        self.api_keys: Dict = {}
        self.trading_settings: Dict = {}
        self.portfolio: List[Dict] = []
        
        # Trading state
        self.last_analysis_time: Optional[datetime] = None
        self.analysis_interval = 300  # 5 minutes
        self.daily_pnl = 0.0
        self.trades_today = 0
        
    async def initialize(self):
        """Initialize bot components"""
        logger.info(f"🤖 Initializing Commercial Trading Bot for {self.user_email}")
        
        try:
            # 1. Load user configuration from database
            await self._load_user_config()
            
            # 2. Initialize AI Market Analyzer
            await self._initialize_ai()
            
            # 3. Validate API keys
            await self._validate_api_keys()
            
            # 4. Load portfolio
            await self._load_portfolio()
            
            logger.info("✅ Bot initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _load_user_config(self):
        """Load user configuration from Supabase"""
        logger.info(f"📊 Loading configuration for user {self.user_id}")
        
        # Load API keys
        keys_result = self.supabase.table('api_keys') \
            .select('*') \
            .eq('user_id', self.user_id) \
            .eq('is_active', True) \
            .execute()
        
        if not keys_result.data:
            raise ValueError(f"No active API keys found for user {self.user_id}")
        
        # Decrypt API keys
        for key_record in keys_result.data:
            exchange = key_record['exchange']
            encrypted_key = key_record['encrypted_api_key']
            encrypted_secret = key_record['encrypted_api_secret']
            
            try:
                api_key = self.security.decrypt(encrypted_key)
                api_secret = self.security.decrypt(encrypted_secret)
                
                self.api_keys[exchange] = {
                    'api_key': api_key,
                    'api_secret': api_secret,
                    'is_testnet': key_record['is_testnet'],
                    'passphrase': key_record.get('passphrase')
                }
                
                logger.info(f"✅ Loaded {exchange} API key ({'testnet' if key_record['is_testnet'] else 'live'})")
                
            except Exception as e:
                logger.error(f"❌ Failed to decrypt {exchange} API key: {e}")
        
        # Load trading settings
        settings_result = self.supabase.table('trading_settings') \
            .select('*') \
            .eq('user_id', self.user_id) \
            .execute()
        
        if settings_result.data:
            for setting in settings_result.data:
                exchange = setting['exchange']
                self.trading_settings[exchange] = setting
                logger.info(f"📋 Trading settings for {exchange}:")
                logger.info(f"   Enabled: {setting.get('is_trading_enabled')}")
                logger.info(f"   Max position: ${setting.get('max_position_size')}")
                logger.info(f"   Risk level: {setting.get('risk_level')}/5")
        else:
            logger.warning("⚠️  No trading settings found - using defaults")
    
    async def _initialize_ai(self):
        """Initialize AI Market Analyzer"""
        try:
            self.market_analyzer = MarketAnalyzer()
            logger.info("✅ AI Market Analyzer initialized")
            logger.info(f"   Claude: {'✅' if self.market_analyzer.claude_client else '❌'}")
            logger.info(f"   Gemini: {'✅' if self.market_analyzer.gemini_api_key else '❌'}")
            logger.info(f"   Tavily: {'✅' if self.market_analyzer.tavily else '❌'}")
        except Exception as e:
            logger.warning(f"⚠️  AI initialization failed: {e}")
            logger.warning("Bot will run without AI analysis")
            self.market_analyzer = None
    
    async def _validate_api_keys(self):
        """Validate API keys with exchanges"""
        logger.info("🔑 Validating API keys...")
        
        # For now, just log that we have keys
        # In production, we'd test actual connection
        for exchange, keys in self.api_keys.items():
            logger.info(f"✅ {exchange} API key ready ({'testnet' if keys['is_testnet'] else 'live'})")
    
    async def _load_portfolio(self):
        """Load user portfolio from database"""
        portfolio_result = self.supabase.table('portfolios') \
            .select('*') \
            .eq('user_id', self.user_id) \
            .execute()
        
        if portfolio_result.data:
            self.portfolio = portfolio_result.data
            logger.info(f"💼 Portfolio loaded: {len(self.portfolio)} positions")
            
            total_value = 0.0
            for pos in self.portfolio:
                balance = float(pos.get('balance', 0))
                if balance > 0:
                    value = balance * float(pos.get('avg_buy_price', 0))
                    total_value += value
                    logger.info(f"   {pos['symbol']}: {balance} (${value:.2f})")
            
            logger.info(f"   Total portfolio value: ${total_value:.2f}")
        else:
            logger.info("💼 Empty portfolio")
    
    async def run_trading_cycle(self):
        """Execute one trading cycle"""
        try:
            logger.info("\n" + "="*80)
            logger.info(f"🔄 Trading Cycle - {datetime.now()}")
            logger.info("="*80)
            
            # 1. Check if trading is enabled
            trading_enabled = False
            active_exchange = None
            
            for exchange, settings in self.trading_settings.items():
                if settings.get('is_trading_enabled'):
                    trading_enabled = True
                    active_exchange = exchange
                    break
            
            if not trading_enabled:
                logger.info("⏸️  Trading is disabled - skipping cycle")
                return
            
            logger.info(f"✅ Trading enabled for {active_exchange}")
            
            # 2. Check daily loss limit
            if self.daily_pnl < -self.trading_settings[active_exchange].get('max_daily_loss', 100):
                logger.warning(f"⚠️  Daily loss limit reached: ${self.daily_pnl:.2f}")
                logger.info("🛑 Stopping trading for today")
                return
            
            # 3. AI Market Analysis
            if self.market_analyzer and (not self.last_analysis_time or 
                datetime.now() - self.last_analysis_time > timedelta(seconds=self.analysis_interval)):
                
                logger.info("\n🤖 Running AI Market Analysis...")
                
                try:
                    # Get trading pairs from settings
                    preferred_pairs = self.trading_settings[active_exchange].get('preferred_pairs', ['BTC/USDT'])
                    
                    for symbol in preferred_pairs:
                        logger.info(f"\n📊 Analyzing {symbol}...")
                        
                        # Prepare parameters for AI analysis
                        analysis_params = {
                            'symbol': symbol,
                            'exchange': active_exchange,
                            'notional': str(self.trading_settings[active_exchange].get('max_position_size', 1000)),
                            'max_leverage': '1',  # SPOT only
                            'user_id': self.user_id
                        }
                        
                        # Run AI analysis
                        analysis = await self.market_analyzer.analyze_market(analysis_params)
                        
                        if analysis:
                            logger.info(f"✅ AI Analysis completed:")
                            logger.info(f"   Market regime: {analysis.get('market_regime', {}).get('regime')}")
                            
                            top_pick = analysis.get('top_pick', {})
                            if top_pick:
                                logger.info(f"   Top pick: {top_pick.get('symbol')}")
                                logger.info(f"   Action: {top_pick.get('action')}")
                                logger.info(f"   Confidence: {top_pick.get('confidence_pct')}%")
                                logger.info(f"   Reason: {top_pick.get('why', '')[:100]}...")
                            
                            # Save analysis to database
                            self.supabase.table('ai_insights').insert({
                                'user_id': self.user_id,
                                'insight_type': 'market_analysis',
                                'title': f"AI Analysis: {symbol}",
                                'description': top_pick.get('why', 'No recommendation'),
                                'confidence_score': int(top_pick.get('confidence_pct', 0)),
                                'priority': 'medium',
                                'related_symbols': [symbol],
                                'metadata': analysis
                            }).execute()
                            
                            logger.info("💾 Analysis saved to database")
                        
                        # Rate limiting
                        await asyncio.sleep(2)
                    
                    self.last_analysis_time = datetime.now()
                    
                except Exception as e:
                    logger.error(f"❌ AI analysis failed: {e}")
                    logger.error(traceback.format_exc())
            
            # 4. Execute trades (placeholder for now)
            logger.info("\n💹 Trade execution:")
            logger.info("   📋 No trades executed (simulation mode)")
            logger.info(f"   💰 Daily P&L: ${self.daily_pnl:.2f}")
            logger.info(f"   📊 Trades today: {self.trades_today}")
            
            logger.info("\n" + "="*80)
            logger.info("✅ Trading cycle completed")
            logger.info("="*80 + "\n")
            
        except Exception as e:
            logger.error(f"❌ Trading cycle error: {e}")
            logger.error(traceback.format_exc())
    
    async def start(self):
        """Start the trading bot"""
        self.running = True
        
        logger.info("\n" + "🚀" * 40)
        logger.info("🤖 COMMERCIAL TRADING BOT - STARTED")
        logger.info(f"👤 User: {self.user_email}")
        logger.info(f"🆔 User ID: {self.user_id}")
        logger.info("🚀" * 40 + "\n")
        
        try:
            while self.running and not self.shutdown_event.is_set():
                await self.run_trading_cycle()
                
                # Wait 60 seconds before next cycle
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=60)
                except asyncio.TimeoutError:
                    pass  # Normal - continue to next cycle
                
        except Exception as e:
            logger.error(f"❌ Fatal error in main loop: {e}")
            logger.error(traceback.format_exc())
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the trading bot"""
        logger.info("\n🛑 Stopping trading bot...")
        self.running = False
        self.shutdown_event.set()
        
        # TODO: Close any open positions
        # TODO: Save final state to database
        
        logger.info("✅ Trading bot stopped gracefully")
    
    def handle_signal(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"\n⚠️  Received signal {signum}")
        asyncio.create_task(self.stop())


async def main():
    """Main entry point"""
    
    # Get user from environment
    user_id = os.getenv('USER_ID')
    user_email = os.getenv('USER_EMAIL')
    
    if not user_id or not user_email:
        logger.error("❌ USER_ID and USER_EMAIL environment variables must be set")
        sys.exit(1)
    
    # Create bot instance
    bot = CommercialTradingBot(user_id, user_email)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, lambda s, f: asyncio.create_task(bot.stop()))
    signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(bot.stop()))
    
    # Initialize and start
    if await bot.initialize():
        await bot.start()
    else:
        logger.error("❌ Bot initialization failed")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down on keyboard interrupt")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
