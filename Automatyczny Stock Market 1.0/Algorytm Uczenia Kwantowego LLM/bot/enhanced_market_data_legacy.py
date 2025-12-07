"""
Enhanced Market Data Manager
Agreguje dane z wielu źródeł: Alpha Vantage, Polygon, CoinGecko, TradingView
"""
import asyncio
import aiohttp
import redis
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass
import os
from alpha_vantage.timeseries import TimeSeries
from pycoingecko import CoinGeckoAPI
import ccxt
import json

logger = logging.getLogger(__name__)

@dataclass
class MarketData:
    symbol: str
    price: float
    volume: float
    timestamp: datetime
    source: str
    metadata: Dict[str, Any] = None

@dataclass
class SentimentData:
    symbol: str
    sentiment_score: float
    source: str
    timestamp: datetime
    details: Dict[str, Any] = None

class EnhancedMarketDataManager:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            decode_responses=True
        )
        
        # API Keys
        self.alpha_vantage_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.polygon_key = os.getenv('POLYGON_API_KEY')
        self.news_api_key = os.getenv('NEWS_API_KEY')
        
        # Clients
        self.coingecko = CoinGeckoAPI()
        self.alpha_vantage = TimeSeries(key=self.alpha_vantage_key) if self.alpha_vantage_key else None
        
        # CCXT Exchanges
        self.exchanges = {
            'binance': ccxt.binance(),
            'coinbase': ccxt.coinbasepro(),
            'kraken': ccxt.kraken(),
            'huobi': ccxt.huobi(),
            'bybit': ccxt.bybit()
        }
        
        # Cache settings
        self.cache_ttl = {
            'price': 60,  # 1 minute
            'volume': 300,  # 5 minutes
            'sentiment': 900,  # 15 minutes
            'news': 1800  # 30 minutes
        }
    
    async def get_aggregated_price(self, symbol: str) -> Dict[str, float]:
        """Pobiera cenę z wielu giełd i oblicza średnią ważoną volumenem"""
        cache_key = f"agg_price:{symbol}"
        cached = self.redis_client.get(cache_key)
        
        if cached:
            return json.loads(cached)
        
        prices = {}
        volumes = {}
        
        # Pobierz z wszystkich dostępnych giełd
        for exchange_name, exchange in self.exchanges.items():
            try:
                if exchange.has['fetchTicker']:
                    ticker = await self._safe_fetch_ticker(exchange, symbol)
                    if ticker:
                        prices[exchange_name] = ticker['last']
                        volumes[exchange_name] = ticker['baseVolume'] or 0
            except Exception as e:
                logger.warning(f"Failed to fetch from {exchange_name}: {e}")
                continue
        
        if not prices:
            return {}
        
        # Oblicz średnią ważoną volumenem
        total_volume = sum(volumes.values())
        if total_volume > 0:
            weighted_price = sum(
                price * volumes[exchange] / total_volume 
                for exchange, price in prices.items()
            )
        else:
            weighted_price = sum(prices.values()) / len(prices)
        
        result = {
            'weighted_price': weighted_price,
            'prices': prices,
            'volumes': volumes,
            'exchanges_count': len(prices),
            'timestamp': datetime.now().isoformat()
        }
        
        # Cache result
        self.redis_client.setex(
            cache_key, 
            self.cache_ttl['price'], 
            json.dumps(result, default=str)
        )
        
        return result
    
    async def _safe_fetch_ticker(self, exchange, symbol):
        """Bezpieczne pobieranie ticker z timeout"""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(exchange.fetch_ticker, symbol),
                timeout=5.0
            )
        except Exception:
            return None
    
    async def get_market_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Agreguje sentiment z wielu źródeł"""
        cache_key = f"sentiment:{symbol}"
        cached = self.redis_client.get(cache_key)
        
        if cached:
            return json.loads(cached)
        
        sentiments = {}
        
        # CoinGecko sentiment
        try:
            cg_data = await self._get_coingecko_sentiment(symbol)
            if cg_data:
                sentiments['coingecko'] = cg_data
        except Exception as e:
            logger.warning(f"CoinGecko sentiment failed: {e}")
        
        # News sentiment
        try:
            news_sentiment = await self._get_news_sentiment(symbol)
            if news_sentiment:
                sentiments['news'] = news_sentiment
        except Exception as e:
            logger.warning(f"News sentiment failed: {e}")
        
        # Social media sentiment (placeholder for future Twitter/Reddit API)
        try:
            social_sentiment = await self._get_social_sentiment(symbol)
            if social_sentiment:
                sentiments['social'] = social_sentiment
        except Exception as e:
            logger.warning(f"Social sentiment failed: {e}")
        
        # Oblicz zagregowany sentiment
        if sentiments:
            scores = [s.get('score', 0) for s in sentiments.values() if 'score' in s]
            avg_sentiment = sum(scores) / len(scores) if scores else 0
            
            result = {
                'aggregated_score': avg_sentiment,
                'individual_sources': sentiments,
                'confidence': len(sentiments) / 3,  # Max 3 sources
                'timestamp': datetime.now().isoformat()
            }
        else:
            result = {
                'aggregated_score': 0,
                'individual_sources': {},
                'confidence': 0,
                'timestamp': datetime.now().isoformat()
            }
        
        # Cache result
        self.redis_client.setex(
            cache_key,
            self.cache_ttl['sentiment'],
            json.dumps(result, default=str)
        )
        
        return result
    
    async def _get_coingecko_sentiment(self, symbol: str) -> Optional[Dict]:
        """Pobiera sentiment z CoinGecko"""
        try:
            # Convert symbol to CoinGecko ID
            coin_id = self._symbol_to_coingecko_id(symbol)
            if not coin_id:
                return None
            
            data = await asyncio.to_thread(
                self.coingecko.get_coin_by_id,
                coin_id,
                localization='false',
                tickers=False,
                market_data=True,
                community_data=True,
                developer_data=False
            )
            
            sentiment_votes = data.get('sentiment_votes_up_percentage', 50)
            market_data = data.get('market_data', {})
            
            # Oblicz sentiment score (-1 do 1)
            sentiment_score = (sentiment_votes - 50) / 50
            
            return {
                'score': sentiment_score,
                'votes_up_percentage': sentiment_votes,
                'market_cap_rank': market_data.get('market_cap_rank'),
                'source': 'coingecko'
            }
        except Exception as e:
            logger.error(f"CoinGecko sentiment error: {e}")
            return None
    
    async def _get_news_sentiment(self, symbol: str) -> Optional[Dict]:
        """Pobiera sentiment z wiadomości (News API)"""
        if not self.news_api_key:
            return None
        
        try:
            # Placeholder - implementacja z News API
            # W rzeczywistości używałbyś NLP do analizy sentymentu artykułów
            return {
                'score': 0.1,  # Placeholder
                'articles_count': 5,
                'source': 'news_api'
            }
        except Exception as e:
            logger.error(f"News sentiment error: {e}")
            return None
    
    async def _get_social_sentiment(self, symbol: str) -> Optional[Dict]:
        """Pobiera sentiment z mediów społecznościowych"""
        try:
            # Placeholder dla Twitter/Reddit API
            return {
                'score': 0.05,  # Placeholder
                'mentions_count': 100,
                'source': 'social_media'
            }
        except Exception as e:
            logger.error(f"Social sentiment error: {e}")
            return None
    
    def _symbol_to_coingecko_id(self, symbol: str) -> Optional[str]:
        """Konwertuje symbol na CoinGecko ID"""
        mapping = {
            'BTC/USDT': 'bitcoin',
            'ETH/USDT': 'ethereum',
            'BNB/USDT': 'binancecoin',
            'ADA/USDT': 'cardano',
            'SOL/USDT': 'solana',
            'DOT/USDT': 'polkadot',
            'AVAX/USDT': 'avalanche-2',
            'MATIC/USDT': 'matic-network'
        }
        return mapping.get(symbol)
    
    async def get_historical_data(self, symbol: str, timeframe: str = '1d', limit: int = 100) -> pd.DataFrame:
        """Pobiera dane historyczne z wielu źródeł"""
        cache_key = f"historical:{symbol}:{timeframe}:{limit}"
        cached = self.redis_client.get(cache_key)
        
        if cached:
            return pd.read_json(cached)
        
        # Próbuj pobrać z najlepszego dostępnego źródła
        for exchange_name, exchange in self.exchanges.items():
            try:
                if exchange.has['fetchOHLCV']:
                    ohlcv = await asyncio.to_thread(
                        exchange.fetch_ohlcv, 
                        symbol, 
                        timeframe, 
                        limit=limit
                    )
                    
                    if ohlcv:
                        df = pd.DataFrame(
                            ohlcv, 
                            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                        )
                        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                        df.set_index('timestamp', inplace=True)
                        
                        # Cache for 5 minutes
                        self.redis_client.setex(
                            cache_key,
                            300,
                            df.to_json()
                        )
                        
                        return df
            except Exception as e:
                logger.warning(f"Failed to fetch historical from {exchange_name}: {e}")
                continue
        
        return pd.DataFrame()
    
    async def get_arbitrage_opportunities(self, symbols: List[str]) -> List[Dict]:
        """Znajduje możliwości arbitrażu między giełdami"""
        opportunities = []
        
        for symbol in symbols:
            try:
                prices = await self.get_aggregated_price(symbol)
                if not prices.get('prices'):
                    continue
                
                exchange_prices = prices['prices']
                if len(exchange_prices) < 2:
                    continue
                
                min_price = min(exchange_prices.values())
                max_price = max(exchange_prices.values())
                
                if min_price > 0:
                    profit_percentage = ((max_price - min_price) / min_price) * 100
                    
                    if profit_percentage > 0.5:  # Min 0.5% profit
                        opportunities.append({
                            'symbol': symbol,
                            'buy_exchange': min(exchange_prices, key=exchange_prices.get),
                            'sell_exchange': max(exchange_prices, key=exchange_prices.get),
                            'buy_price': min_price,
                            'sell_price': max_price,
                            'profit_percentage': profit_percentage,
                            'timestamp': datetime.now().isoformat()
                        })
            except Exception as e:
                logger.error(f"Arbitrage check failed for {symbol}: {e}")
                continue
        
        return sorted(opportunities, key=lambda x: x['profit_percentage'], reverse=True)
    
    async def health_check(self) -> Dict[str, Any]:
        """Sprawdza stan wszystkich połączeń"""
        status = {
            'redis': False,
            'exchanges': {},
            'apis': {}
        }
        
        # Redis check
        try:
            self.redis_client.ping()
            status['redis'] = True
        except:
            pass
        
        # Exchange checks
        for name, exchange in self.exchanges.items():
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(exchange.fetch_status),
                    timeout=5.0
                )
                status['exchanges'][name] = True
            except:
                status['exchanges'][name] = False
        
        # API checks
        status['apis']['alpha_vantage'] = bool(self.alpha_vantage_key)
        status['apis']['polygon'] = bool(self.polygon_key)
        status['apis']['news_api'] = bool(self.news_api_key)
        
        return status

# Singleton instance
_market_data_manager = None

def get_market_data_manager() -> EnhancedMarketDataManager:
    global _market_data_manager
    if _market_data_manager is None:
        _market_data_manager = EnhancedMarketDataManager()
    return _market_data_manager
