"""
Bot Manager - zarządza instancjami botów dla użytkowników.
Uruchamia i zatrzymuje boty na podstawie stanu w bazie danych.
Automatycznie wznawia boty po restarcie serwera.
"""

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime

from bot.auto_trader import AutomatedTradingBot
from bot.db import DatabaseManager

logger = logging.getLogger(__name__)


class BotManager:
    """Singleton manager for all user trading bots."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.active_bots: Dict[str, AutomatedTradingBot] = {}
        self.bot_tasks: Dict[str, asyncio.Task] = {}
        self.running = False
        self._initialized = True
        self._initial_sync_done = False
        self._sync_task: Optional[asyncio.Task] = None
        logger.info("BotManager initialized")
    
    async def start_bot_for_user(
        self,
        user_id: str,
        api_key: str,
        api_secret: str,
        exchange_name: str = "binance",
        testnet: bool = False,
        futures: bool = True
    ) -> bool:
        """Start a trading bot for a specific user."""
        
        if user_id in self.active_bots:
            logger.warning(f"Bot already running for user {user_id}")
            return False
        
        try:
            # Create bot instance
            bot = AutomatedTradingBot(
                api_key=api_key,
                api_secret=api_secret,
                exchange_name=exchange_name,
                user_id=user_id,
                test_mode=testnet,
                futures=futures
            )
            
            # Initialize bot
            await bot.initialize()
            
            # Store bot instance
            self.active_bots[user_id] = bot
            
            # Create and store async task
            task = asyncio.create_task(self._run_bot(user_id, bot))
            self.bot_tasks[user_id] = task
            
            logger.info(f"✅ Bot started for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start bot for user {user_id}: {e}")
            return False
    
    async def _run_bot(self, user_id: str, bot: AutomatedTradingBot):
        """Run the bot's main loop."""
        try:
            await bot.run_forever()
        except asyncio.CancelledError:
            logger.info(f"Bot task cancelled for user {user_id}")
        except Exception as e:
            logger.error(f"Bot error for user {user_id}: {e}")
        finally:
            await self._cleanup_bot(user_id)
    
    async def stop_bot_for_user(self, user_id: str) -> bool:
        """Stop a running bot for a specific user."""
        
        if user_id not in self.active_bots:
            logger.warning(f"No active bot found for user {user_id}")
            return False
        
        try:
            # Cancel the task
            if user_id in self.bot_tasks:
                self.bot_tasks[user_id].cancel()
                try:
                    await self.bot_tasks[user_id]
                except asyncio.CancelledError:
                    pass
            
            # Shutdown the bot
            bot = self.active_bots[user_id]
            await bot.shutdown()
            
            # Cleanup
            await self._cleanup_bot(user_id)
            
            logger.info(f"✅ Bot stopped for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop bot for user {user_id}: {e}")
            return False
    
    async def _cleanup_bot(self, user_id: str):
        """Remove bot from active bots."""
        if user_id in self.active_bots:
            del self.active_bots[user_id]
        if user_id in self.bot_tasks:
            del self.bot_tasks[user_id]
    
    def is_bot_running(self, user_id: str) -> bool:
        """Check if bot is running for user."""
        return user_id in self.active_bots
    
    def get_active_bot_count(self) -> int:
        """Get number of active bots."""
        return len(self.active_bots)
    
    def get_active_user_ids(self) -> list:
        """Get list of user IDs with active bots."""
        return list(self.active_bots.keys())
    
    async def sync_with_database(self):
        """
        Sync bot states with database.
        Start bots for users with is_trading_enabled=True.
        Stop bots for users with is_trading_enabled=False.
        """
        try:
            with DatabaseManager() as db:
                # Query TradingSettings to find enabled bots
                from bot.models_legacy import TradingSettings, ExchangeAPIKey
                
                # Get all users with trading enabled
                enabled_settings = (
                    db.session.query(TradingSettings)
                    .filter(TradingSettings.is_trading_enabled == True)
                    .all()
                )
                
                enabled_user_ids = {str(s.user_id) for s in enabled_settings}
                current_user_ids = set(self.active_bots.keys())
                
                # Start bots for newly enabled users
                users_to_start = enabled_user_ids - current_user_ids
                for user_id in users_to_start:
                    # Get API keys for user
                    api_key = (
                        db.session.query(ExchangeAPIKey)
                        .filter(ExchangeAPIKey.user_id == user_id)
                        .filter(ExchangeAPIKey.is_active == True)
                        .first()
                    )
                    
                    if api_key:
                        settings = next(
                            (s for s in enabled_settings if str(s.user_id) == user_id),
                            None
                        )
                        
                        await self.start_bot_for_user(
                            user_id=user_id,
                            api_key=api_key.api_key,
                            api_secret=api_key.api_secret,
                            exchange_name=api_key.exchange or "binance",
                            testnet=api_key.is_testnet if hasattr(api_key, 'is_testnet') else False,
                            futures=True
                        )
                    else:
                        logger.warning(f"No active API key found for user {user_id}")
                
                # Stop bots for disabled users
                users_to_stop = current_user_ids - enabled_user_ids
                for user_id in users_to_stop:
                    await self.stop_bot_for_user(user_id)
                
                logger.info(
                    f"Bot sync complete: {len(users_to_start)} started, "
                    f"{len(users_to_stop)} stopped, {self.get_active_bot_count()} active"
                )
                
        except Exception as e:
            logger.error(f"Failed to sync bots with database: {e}")
    
    async def resume_all_bots(self):
        """
        Resume all bots that should be running after server restart.
        This is called once at startup to restore previous state.
        """
        if self._initial_sync_done:
            logger.info("Initial sync already done, skipping resume_all_bots")
            return
            
        logger.info("🔄 Resuming bots after server restart...")
        
        try:
            await self.sync_with_database()
            self._initial_sync_done = True
            logger.info(f"✅ Bot resume complete: {self.get_active_bot_count()} bots running")
        except Exception as e:
            logger.error(f"Failed to resume bots: {e}")
    
    async def start_sync_loop(self, interval_seconds: int = 30):
        """
        Start background loop to sync bots with database.
        Also performs initial bot resume on first run.
        """
        self.running = True
        logger.info(f"Starting bot sync loop (interval: {interval_seconds}s)")
        
        # CRITICAL FIX: Perform initial resume before starting the loop
        if not self._initial_sync_done:
            logger.info("🚀 Performing initial bot resume...")
            await self.resume_all_bots()
        
        while self.running:
            try:
                await self.sync_with_database()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                logger.info("Sync loop cancelled")
                break
            except Exception as e:
                logger.error(f"Sync loop error: {e}")
                await asyncio.sleep(interval_seconds)
        
        logger.info("Bot sync loop stopped")
    
    async def stop_all_bots(self):
        """Stop all running bots."""
        self.running = False
        
        # Cancel sync task if running
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        
        user_ids = list(self.active_bots.keys())
        for user_id in user_ids:
            await self.stop_bot_for_user(user_id)
        
        logger.info("All bots stopped")
    
    def get_bot_status(self, user_id: str) -> Optional[Dict]:
        """Get detailed status of a user's bot."""
        if user_id not in self.active_bots:
            return None
        
        bot = self.active_bots[user_id]
        task = self.bot_tasks.get(user_id)
        
        return {
            "user_id": user_id,
            "running": task and not task.done() if task else False,
            "exchange": bot.exchange_name if hasattr(bot, 'exchange_name') else "unknown",
            "started_at": bot.started_at if hasattr(bot, 'started_at') else None,
            "last_cycle": bot.trading_engine.last_run if bot.trading_engine else None,
            "strategies_count": len(bot.trading_engine.strategies) if bot.trading_engine else 0,
        }
    
    def get_all_bot_statuses(self) -> List[Dict]:
        """Get status of all active bots."""
        return [
            self.get_bot_status(user_id) 
            for user_id in self.active_bots.keys()
        ]


# Global bot manager instance
bot_manager = BotManager()
