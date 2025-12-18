import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import aiohttp
from sqlalchemy import select, desc

from bot.db import DatabaseManager, Trade, TradingSignal, extract_base_symbol
from bot.ai_analysis import MarketAnalyzer
from bot.tavily_web_search import TavilyWebSearch

logger = logging.getLogger(__name__)

class MarketAnalysisService:
    """
    Service to perform market analysis using the same pipeline as the 'AI trading signals' Edge Function.
    Fetches data from Supabase (historical trades/signals), Twitter (twitterapi.io), and Tavily (News).
    """

    def __init__(self, db_manager: DatabaseManager, market_analyzer: MarketAnalyzer):
        self.db = db_manager
        self.analyzer = market_analyzer
        self.twitter_api_key = os.getenv("TWITTER_API_KEY")
        self.tavily_api_key = os.getenv("TAVILY_API_KEY")
        self.tavily = TavilyWebSearch(api_key=self.tavily_api_key) if self.tavily_api_key else None

    async def fetch_historical_data(self, symbol: str, limit: int = 1000) -> Dict[str, Any]:
        """Fetch historical trades and signals from Supabase."""
        logger.info(f"📊 [DB] Fetching historical data for {symbol}...")
        
        # Use base symbol for signal queries (signals stored as BTC, ETH, etc.)
        base_symbol = extract_base_symbol(symbol)
        # Keep original pair format for trades (stored with full pair)
        symbol_pair = f"{symbol}/USDT" if '/' not in symbol else symbol
        
        with self.db as session:
            # Fetch trades (may still use full pair format)
            trades_query = (
                select(Trade)
                .where(Trade.symbol == symbol_pair)
                .where(Trade.pnl.is_not(None))
                .order_by(desc(Trade.created_at))
                .limit(limit)
            )
            trades = session.session.execute(trades_query).scalars().all()
            
            # Fetch signals - use base symbol (BTC, ETH, etc.)
            signals_query = (
                select(TradingSignal)
                .where(TradingSignal.symbol == base_symbol)  # Use base symbol
                .order_by(desc(TradingSignal.created_at))
                .limit(min(limit, 5000))
            )
            signals = session.session.execute(signals_query).scalars().all()
            
            logger.info(f"✅ [DB] Fetched {len(trades)} trades, {len(signals)} signals")
            
            # Convert to dicts for easier processing
            trades_data = [
                {
                    "symbol": t.symbol,
                    "trade_type": t.trade_type,
                    "price": t.price,
                    "amount": t.amount,
                    "pnl": t.pnl,
                    "created_at": t.created_at.isoformat(),
                    "source": t.source,
                    "emotion": t.emotion
                } for t in trades
            ]
            
            signals_data = [
                {
                    "symbol": s.symbol,
                    "signal_type": s.signal_type,
                    "strength": s.strength,
                    "confidence_score": s.confidence_score,
                    "price_target": s.price_target,
                    "created_at": s.created_at.isoformat(),
                    "ai_analysis": s.ai_analysis,
                    "source": s.source
                } for s in signals
            ]
            
            stats = self._calculate_trade_stats(trades_data, signals_data, symbol)
            
            return {
                "trades": trades_data,
                "signals": signals_data,
                "stats": stats
            }

    def _calculate_trade_stats(self, trades: List[Dict], signals: List[Dict], symbol: str) -> Dict:
        """Calculate trading statistics per symbol (Ported from TS)."""
        symbol_key = f"{symbol}/USDT"
        symbol_trades = [t for t in trades if t['symbol'] == symbol_key]
        wins = [t for t in symbol_trades if t['pnl'] > 0]
        losses = [t for t in symbol_trades if t['pnl'] < 0]
        
        # Calculate best performance time (hour of day)
        hourly_performance = {}
        for t in symbol_trades:
            hour = datetime.fromisoformat(t['created_at']).hour
            if hour not in hourly_performance:
                hourly_performance[hour] = {"wins": 0, "total": 0}
            hourly_performance[hour]["total"] += 1
            if t['pnl'] > 0:
                hourly_performance[hour]["wins"] += 1
        
        best_hour = 0
        best_win_rate = 0
        for hour, perf in hourly_performance.items():
            win_rate = (perf["wins"] / perf["total"]) if perf["total"] >= 5 else 0
            if win_rate > best_win_rate:
                best_win_rate = win_rate
                best_hour = hour
                
        # Calculate recent streak
        streak_count = 0
        streak_type = 'neutral'
        if symbol_trades:
            recent_trades = symbol_trades[:10]
            streak_type = 'win' if recent_trades[0]['pnl'] > 0 else 'loss'
            for trade in recent_trades:
                is_win = trade['pnl'] > 0
                if (streak_type == 'win' and is_win) or (streak_type == 'loss' and not is_win):
                    streak_count += 1
                else:
                    break
        
        total_pnl = sum(t['pnl'] for t in symbol_trades)
        avg_win = sum(t['pnl'] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(abs(t['pnl']) for t in losses) / len(losses) if losses else 0
        
        best_trade = max([t['pnl'] for t in symbol_trades]) if symbol_trades else 0
        worst_trade = min([t['pnl'] for t in symbol_trades]) if symbol_trades else 0
        
        best_perf_time = None
        if best_win_rate >= 0.6:
            best_perf_time = f"{best_hour:02d}:00-{(best_hour + 1) % 24:02d}:00 UTC"
            
        return {
            "totalTrades": len(symbol_trades),
            "winRate": (len(wins) / len(symbol_trades) * 100) if symbol_trades else 0,
            "avgWin": avg_win,
            "avgLoss": avg_loss,
            "totalPnL": total_pnl,
            "bestTrade": best_trade,
            "worstTrade": worst_trade,
            "bestPerformanceTime": best_perf_time,
            "recentStreak": streak_type if streak_count >= 3 else None,
            "streakCount": streak_count if streak_count >= 3 else None
        }

    def _format_historical_context(self, historical: Dict, symbol: str) -> str:
        """Format historical data into compact string for AI prompt."""
        stats = historical["stats"]
        
        if stats["totalTrades"] == 0:
            return f"\n\n📊 HISTORICAL DATA: No past trades found for {symbol}."
            
        context = f"\n\n📊 HISTORICAL TRADING DATA FOR {symbol}:\n\n"
        context += f"PERFORMANCE SUMMARY ({stats['totalTrades']} trades):\n"
        context += f"- Win Rate: {stats['winRate']:.1f}% ({int(stats['totalTrades'] * stats['winRate'] / 100)} wins)\n"
        context += f"- Avg Win: ${stats['avgWin']:.2f} | Avg Loss: ${stats['avgLoss']:.2f}\n"
        context += f"- Total PnL: {'+' if stats['totalPnL'] >= 0 else ''}${stats['totalPnL']:.2f}\n"
        context += f"- Best Trade: +${stats['bestTrade']:.2f} | Worst: ${stats['worstTrade']:.2f}\n"
        
        if stats.get("bestPerformanceTime"):
            context += f"- Best Performance Time: {stats['bestPerformanceTime']}\n"
            
        if stats.get("recentStreak") and stats.get("streakCount"):
            context += f"- ⚠️ Current {stats['recentStreak'].upper()} Streak: {stats['streakCount']} trades\n"
            
        # Recent trades
        trades = historical["trades"]
        if trades:
            context += "\nRECENT TRADES (Last 20):\n"
            for i, trade in enumerate(trades[:20]):
                date = trade['created_at'].replace('T', ' ')[:16]
                result = '✅' if trade['pnl'] > 0 else '❌'
                pnl_str = f"+${trade['pnl']:.0f}" if trade['pnl'] >= 0 else f"${trade['pnl']:.0f}"
                context += f"{i + 1}. {date} | {trade['trade_type'].upper()} ${trade['price']:.2f} = {pnl_str} ({trade['source']}) {result}\n"
        
        return context

    async def fetch_crypto_tweets(self, symbol: str, max_results: int = 10) -> List[Dict]:
        """Fetch tweets using twitterapi.io (Ported from TS)."""
        if not self.twitter_api_key:
            logger.warning("⚠️ [TWITTER] API Key not set - skipping tweets")
            return []
            
        logger.info(f"🐦 [TWITTER] Fetching tweets for {symbol}...")
        
        try:
            query = f"{symbol} OR ${symbol} crypto OR cryptocurrency"
            url = "https://api.twitterapi.io/twitter/tweet/advanced_search"
            params = {
                "query": query,
                "queryType": "Latest"
            }
            headers = {"X-API-Key": self.twitter_api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"❌ [TWITTER] API error: {response.status}")
                        return []
                        
                    data = await response.json()
                    tweets = data.get("tweets", [])
                    
                    if not tweets:
                        logger.warning(f"⚠️ [TWITTER] No tweets found for {symbol}")
                        return []
                        
                    processed_tweets = []
                    for t in tweets[:max_results]:
                        author = t.get("author", {})
                        processed_tweets.append({
                            "text": t.get("text", ""),
                            "author": author.get("userName", "unknown"),
                            "likes": t.get("likeCount", 0),
                            "retweets": t.get("retweetCount", 0)
                        })
                        
                    logger.info(f"✅ [TWITTER] Processed {len(processed_tweets)} tweets")
                    return processed_tweets
                    
        except Exception as e:
            logger.error(f"❌ [TWITTER] Error fetching tweets: {e}")
            return []

    def _format_tweets_for_ai(self, tweets: List[Dict], symbol: str) -> str:
        if not tweets:
            return f"\n\n(No recent tweets available for {symbol})"
            
        text = f"\n\nRecent tweets about {symbol} from Twitter/X ({datetime.now().isoformat()}):\n"
        for i, t in enumerate(tweets):
            text += f"{i + 1}. @{t['author']}: \"{t['text']}\" ({t['likes']} likes, {t['retweets']} RTs)\n"
        return text

    async def fetch_crypto_news(self, symbol: str) -> List[str]:
        """Fetch news using Tavily."""
        if not self.tavily:
            return []
            
        try:
            logger.info(f"🔍 [TAVILY] Fetching news for {symbol}...")
            results = await self.tavily.search_crypto_news(symbol=symbol, max_results=5)
            
            news_items = []
            for r in results:
                date = r.get("published_date", "unknown date")
                news_items.append(f"[{date}] {r.get('title')}: {r.get('content')}")
                
            return news_items
        except Exception as e:
            logger.error(f"❌ [TAVILY] Error: {e}")
            return []

    async def _fetch_signals_from_rust(self) -> List[Dict]:
        """Run Rust client to fetch signals from Edge Function."""
        # FIX 2025-12-17: Updated path for macOS environment
        rust_project_dir = "/Users/filipsliwa/Desktop/ASE BOT/ASE BOT - bot tradingowy/Automatyczny Stock Market 1.0/Algorytm Uczenia Kwantowego LLM/rust_edge_function_test"
        signals_file = os.path.join(rust_project_dir, "signals.json")
        
        logger.info("🦀 [RUST] Executing Rust Edge Function client...")
        
        try:
            # Run cargo run (or the binary directly if built)
            # Using cargo run ensures it compiles if needed, but is slower.
            # For production, running the binary in target/release is better.
            # We'll use cargo run for now as per testing.
            process = await asyncio.create_subprocess_exec(
                "cargo", "run",
                cwd=rust_project_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"❌ [RUST] Execution failed: {stderr.decode()}")
                return []
                
            logger.info(f"✅ [RUST] Execution successful. Output: {len(stdout)} bytes")
            
            # Read signals.json
            if os.path.exists(signals_file):
                with open(signals_file, 'r') as f:
                    signals = json.load(f)
                    logger.info(f"✅ [RUST] Loaded {len(signals)} signals from file")
                    return signals
            else:
                logger.error(f"❌ [RUST] signals.json not found at {signals_file}")
                return []
                
        except Exception as e:
            logger.error(f"❌ [RUST] Error executing Rust client: {e}")
            return []

    async def generate_signal(self, symbol: str, market_data: Dict) -> Optional[Dict]:
        """Generate trading signal using the Rust Edge Function client."""
        logger.info(f"🎯 [SIGNAL] Generating signal for {symbol} via Rust Bridge...")
        
        # Call Rust client (fetches all signals at once)
        # Optimization: We could cache this result if multiple symbols are analyzed in sequence
        # But for now, we'll call it per symbol or rely on the fact that the Rust client fetches all.
        # Ideally, the bot calls this once per cycle for all symbols.
        # However, the current architecture calls generate_signal per symbol.
        # To avoid spamming the Edge Function, we should check if we have a recent signals.json
        # or just let it run. Given the request, we'll run it.
        
        signals = await self._fetch_signals_from_rust()
        
        # Normalize to base symbol for comparison (signals stored as BTC, ETH, etc.)
        base_symbol = extract_base_symbol(symbol)
        
        # Find signal for the requested symbol
        for signal in signals:
            signal_base = extract_base_symbol(signal.get("symbol", ""))
            if signal_base == base_symbol:
                logger.info(f"✅ [RUST] Found signal for {symbol}: {signal.get('action')}")
                return signal
                
        logger.warning(f"⚠️ [RUST] No signal found for {symbol} in Rust output")
        
        # Fallback to local analysis if Rust fails?
        # For now, returning None as per "replace" instruction.
        return None
