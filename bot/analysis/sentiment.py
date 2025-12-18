"""AI Sentiment Analysis Engine (ASAE) - Real-time market sentiment analysis."""

import asyncio
import aiohttp
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from dataclasses import dataclass
import re
import json
import logging
from textblob import TextBlob
import openai
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class SentimentSignal:
    """Represents a sentiment-based trading signal."""
    symbol: str
    sentiment_score: float  # -100 to +100
    confidence: float  # 0-1
    sources: List[str]
    signal_type: str  # bullish/bearish/neutral
    strength: float  # 0-100
    timestamp: datetime
    keywords: List[str]
    volume_spike: bool


@dataclass 
class SocialMetrics:
    """Social media metrics for a symbol."""
    mentions_count: int
    sentiment_avg: float
    sentiment_std: float
    influencer_sentiment: float
    retail_sentiment: float
    smart_money_sentiment: float
    fomo_index: float  # 0-100
    fud_index: float   # 0-100


class AISentimentAnalyzer:
    """
    AI-powered Sentiment Analysis Engine.
    Analyzes social media, news, and on-chain data for trading signals.
    """
    
    def __init__(self, config: Dict = None):
        """Initialize sentiment analyzer."""
        self.config = config or {}
        
        # API configurations
        self.twitter_bearer_token = config.get('twitter_token', '')
        self.reddit_client_id = config.get('reddit_client_id', '')
        self.news_api_key = config.get('news_api_key', '')
        
        # Analysis parameters
        self.sentiment_window = 3600  # 1 hour window
        self.min_mentions_threshold = 10
        self.influencer_weight = 2.0
        self.sentiment_smoothing = 0.3
        
        # Keywords and patterns
        self.bullish_keywords = [
            'moon', 'bullish', 'pump', 'buy', 'long', 'breakout', 'rally',
            'ath', 'all time high', 'rocket', 'lambo', 'gem', 'undervalued'
        ]
        
        self.bearish_keywords = [
            'dump', 'bearish', 'sell', 'short', 'crash', 'scam', 'rug',
            'overvalued', 'bubble', 'correction', 'capitulation', 'fud'
        ]
        
        # Storage
        self.sentiment_history: Dict[str, deque] = {}
        self.alerts_history: List[SentimentSignal] = []
        self.influencer_list = self._load_influencers()
        
    def _load_influencers(self) -> Dict[str, float]:
        """Load crypto influencer list with credibility scores."""
        # In production, this would load from a database
        return {
            "elonmusk": 0.7,
            "michael_saylor": 0.9,
            "APompliano": 0.8,
            "CryptoWhale": 0.85,
            "WhalePanda": 0.8,
            "VitalikButerin": 0.95,
            "cz_binance": 0.9,
            "arthur_0x": 0.85,
            "zhusu": 0.85,
            "AltcoinPsycho": 0.75
        }
    
    async def analyze_sentiment(self, symbol: str) -> Dict:
        """
        Perform comprehensive sentiment analysis for a symbol.
        
        Returns:
            Complete sentiment analysis with signals
        """
        try:
            # Gather data from multiple sources concurrently
            tasks = [
                self._analyze_twitter(symbol),
                self._analyze_reddit(symbol),
                self._analyze_news(symbol),
                self._analyze_google_trends(symbol),
                self._analyze_onchain_sentiment(symbol)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            twitter_data = results[0] if not isinstance(results[0], Exception) else {}
            reddit_data = results[1] if not isinstance(results[1], Exception) else {}
            news_data = results[2] if not isinstance(results[2], Exception) else {}
            trends_data = results[3] if not isinstance(results[3], Exception) else {}
            onchain_data = results[4] if not isinstance(results[4], Exception) else {}
            
            # Aggregate sentiment scores
            aggregated_sentiment = self._aggregate_sentiment({
                'twitter': twitter_data,
                'reddit': reddit_data,
                'news': news_data,
                'trends': trends_data,
                'onchain': onchain_data
            })
            
            # Calculate social metrics
            social_metrics = self._calculate_social_metrics(
                twitter_data, reddit_data, aggregated_sentiment
            )
            
            # Generate sentiment signals
            signals = self._generate_sentiment_signals(
                symbol, aggregated_sentiment, social_metrics
            )
            
            # AI-powered analysis
            ai_insights = await self._get_ai_insights(
                symbol, aggregated_sentiment, social_metrics
            )
            
            return {
                "symbol": symbol,
                "overall_sentiment": aggregated_sentiment,
                "social_metrics": social_metrics,
                "signals": signals,
                "ai_insights": ai_insights,
                "sources": {
                    "twitter": twitter_data,
                    "reddit": reddit_data,
                    "news": news_data,
                    "trends": trends_data,
                    "onchain": onchain_data
                },
                "timestamp": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment for {symbol}: {e}")
            return {}
    
    async def _analyze_twitter(self, symbol: str) -> Dict:
        """Analyze Twitter/X sentiment."""
        if not self.twitter_bearer_token:
            return {}
            
        try:
            # Search parameters
            query = f"${symbol} OR #{symbol} -is:retweet lang:en"
            max_results = 100
            
            # Twitter API v2 endpoint
            url = "https://api.twitter.com/2/tweets/search/recent"
            headers = {"Authorization": f"Bearer {self.twitter_bearer_token}"}
            params = {
                "query": query,
                "max_results": max_results,
                "tweet.fields": "author_id,created_at,public_metrics",
                "user.fields": "username,verified,public_metrics"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status != 200:
                        return {}
                    
                    data = await response.json()
                    tweets = data.get('data', [])
                    
            # Analyze tweets
            sentiments = []
            influencer_sentiments = []
            total_engagement = 0
            
            for tweet in tweets:
                # Basic sentiment analysis
                text = tweet.get('text', '')
                sentiment = self._analyze_text_sentiment(text)
                
                # Check if from influencer
                author_id = tweet.get('author_id', '')
                is_influencer = author_id in self.influencer_list
                
                # Weight by engagement
                metrics = tweet.get('public_metrics', {})
                engagement = (
                    metrics.get('retweet_count', 0) * 2 +
                    metrics.get('like_count', 0) +
                    metrics.get('reply_count', 0) * 1.5
                )
                
                weighted_sentiment = sentiment * (1 + np.log1p(engagement) / 10)
                
                if is_influencer:
                    influencer_sentiments.append(weighted_sentiment)
                else:
                    sentiments.append(weighted_sentiment)
                    
                total_engagement += engagement
            
            # Calculate metrics
            avg_sentiment = np.mean(sentiments) if sentiments else 0
            influencer_sentiment = np.mean(influencer_sentiments) if influencer_sentiments else avg_sentiment
            
            # Detect unusual activity
            volume_spike = len(tweets) > self.min_mentions_threshold * 3
            
            return {
                "tweet_count": len(tweets),
                "avg_sentiment": avg_sentiment,
                "influencer_sentiment": influencer_sentiment,
                "engagement_total": total_engagement,
                "volume_spike": volume_spike,
                "top_keywords": self._extract_keywords(tweets)
            }
            
        except Exception as e:
            logger.error(f"Twitter analysis error: {e}")
            return {}
    
    async def _analyze_reddit(self, symbol: str) -> Dict:
        """Analyze Reddit sentiment."""
        try:
            # Subreddits to monitor
            subreddits = ['cryptocurrency', 'cryptomarkets', 'wallstreetbets', 'satoshistreetbets']
            
            sentiments = []
            post_count = 0
            
            for subreddit in subreddits:
                url = f"https://www.reddit.com/r/{subreddit}/search.json"
                params = {
                    'q': symbol,
                    'sort': 'new',
                    'limit': 25,
                    't': 'hour'
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params) as response:
                        if response.status != 200:
                            continue
                            
                        data = await response.json()
                        posts = data.get('data', {}).get('children', [])
                        
                        for post in posts:
                            post_data = post.get('data', {})
                            title = post_data.get('title', '')
                            selftext = post_data.get('selftext', '')
                            score = post_data.get('score', 0)
                            
                            # Analyze sentiment
                            text = f"{title} {selftext}"
                            sentiment = self._analyze_text_sentiment(text)
                            
                            # Weight by score
                            weighted_sentiment = sentiment * (1 + np.log1p(abs(score)) / 5)
                            sentiments.append(weighted_sentiment)
                            post_count += 1
            
            avg_sentiment = np.mean(sentiments) if sentiments else 0
            
            return {
                "post_count": post_count,
                "avg_sentiment": avg_sentiment,
                "subreddit_activity": len(sentiments)
            }
            
        except Exception as e:
            logger.error(f"Reddit analysis error: {e}")
            return {}
    
    async def _analyze_news(self, symbol: str) -> Dict:
        """Analyze news sentiment."""
        try:
            # News sources for crypto
            sources = ['coindesk', 'cointelegraph', 'decrypt', 'bitcoinmagazine']
            
            url = "https://newsapi.org/v2/everything"
            params = {
                'q': symbol,
                'sources': ','.join(sources),
                'sortBy': 'publishedAt',
                'apiKey': self.news_api_key,
                'pageSize': 20
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        return {}
                        
                    data = await response.json()
                    articles = data.get('articles', [])
            
            sentiments = []
            for article in articles:
                title = article.get('title', '')
                description = article.get('description', '')
                
                text = f"{title} {description}"
                sentiment = self._analyze_text_sentiment(text)
                sentiments.append(sentiment)
            
            avg_sentiment = np.mean(sentiments) if sentiments else 0
            
            return {
                "article_count": len(articles),
                "avg_sentiment": avg_sentiment,
                "recent_headlines": [a.get('title', '') for a in articles[:5]]
            }
            
        except Exception as e:
            logger.error(f"News analysis error: {e}")
            return {}
    
    async def _analyze_google_trends(self, symbol: str) -> Dict:
        """Analyze Google Trends data."""
        # Simplified implementation - in production would use pytrends
        try:
            # Simulate trends data
            trend_score = np.random.randint(0, 100)
            trend_direction = "increasing" if trend_score > 50 else "decreasing"
            
            return {
                "trend_score": trend_score,
                "trend_direction": trend_direction,
                "search_volume": trend_score * 1000
            }
        except Exception as e:
            logger.error(f"Google Trends error: {e}")
            return {}
    
    async def _analyze_onchain_sentiment(self, symbol: str) -> Dict:
        """Analyze on-chain metrics for sentiment."""
        try:
            # In production, this would connect to on-chain data providers
            # Simulating on-chain metrics
            
            return {
                "whale_accumulation": np.random.choice([True, False]),
                "exchange_netflow": np.random.uniform(-1000000, 1000000),
                "active_addresses": np.random.randint(10000, 100000),
                "transaction_volume": np.random.uniform(1000000, 10000000)
            }
        except Exception as e:
            logger.error(f"On-chain analysis error: {e}")
            return {}
    
    def _analyze_text_sentiment(self, text: str) -> float:
        """Analyze sentiment of text using TextBlob and keyword matching."""
        # Clean text
        text = text.lower()
        
        # TextBlob sentiment
        blob = TextBlob(text)
        base_sentiment = blob.sentiment.polarity  # -1 to 1
        
        # Keyword analysis
        bullish_count = sum(1 for keyword in self.bullish_keywords if keyword in text)
        bearish_count = sum(1 for keyword in self.bearish_keywords if keyword in text)
        
        keyword_sentiment = (bullish_count - bearish_count) * 0.1
        
        # Combine sentiments
        combined_sentiment = (base_sentiment + keyword_sentiment) * 50  # Scale to -100 to 100
        
        return max(-100, min(100, combined_sentiment))
    
    def _aggregate_sentiment(self, sources: Dict) -> Dict:
        """Aggregate sentiment from all sources."""
        sentiments = []
        weights = {
            'twitter': 0.3,
            'reddit': 0.2,
            'news': 0.25,
            'trends': 0.15,
            'onchain': 0.1
        }
        
        weighted_sum = 0
        total_weight = 0
        
        for source, data in sources.items():
            if data and 'avg_sentiment' in data:
                sentiment = data['avg_sentiment']
                weight = weights.get(source, 0.1)
                weighted_sum += sentiment * weight
                total_weight += weight
                sentiments.append(sentiment)
        
        overall_sentiment = weighted_sum / total_weight if total_weight > 0 else 0
        sentiment_std = np.std(sentiments) if sentiments else 0
        
        # Determine market mood
        if overall_sentiment > 30:
            mood = "Extremely Bullish"
        elif overall_sentiment > 10:
            mood = "Bullish"
        elif overall_sentiment > -10:
            mood = "Neutral"
        elif overall_sentiment > -30:
            mood = "Bearish"
        else:
            mood = "Extremely Bearish"
        
        return {
            "score": overall_sentiment,
            "std_dev": sentiment_std,
            "mood": mood,
            "confidence": min(0.9, 1 - sentiment_std / 100)
        }
    
    def _calculate_social_metrics(self, twitter_data: Dict, reddit_data: Dict, 
                                 aggregated: Dict) -> SocialMetrics:
        """Calculate comprehensive social metrics."""
        # Total mentions
        mentions = (
            twitter_data.get('tweet_count', 0) + 
            reddit_data.get('post_count', 0)
        )
        
        # Sentiment metrics
        sentiment_avg = aggregated.get('score', 0)
        sentiment_std = aggregated.get('std_dev', 0)
        
        # Different sentiment types
        influencer_sentiment = twitter_data.get('influencer_sentiment', sentiment_avg)
        retail_sentiment = (
            twitter_data.get('avg_sentiment', 0) * 0.6 +
            reddit_data.get('avg_sentiment', 0) * 0.4
        )
        
        # Smart money sentiment (influencers + on-chain)
        smart_money_sentiment = influencer_sentiment * 0.7 + sentiment_avg * 0.3
        
        # FOMO/FUD indices
        if sentiment_avg > 20 and twitter_data.get('volume_spike', False):
            fomo_index = min(100, sentiment_avg + 20)
        else:
            fomo_index = max(0, sentiment_avg)
            
        fud_index = max(0, -sentiment_avg) if sentiment_avg < -20 else 0
        
        return SocialMetrics(
            mentions_count=mentions,
            sentiment_avg=sentiment_avg,
            sentiment_std=sentiment_std,
            influencer_sentiment=influencer_sentiment,
            retail_sentiment=retail_sentiment,
            smart_money_sentiment=smart_money_sentiment,
            fomo_index=fomo_index,
            fud_index=fud_index
        )
    
    def _generate_sentiment_signals(self, symbol: str, aggregated: Dict, 
                                   metrics: SocialMetrics) -> List[SentimentSignal]:
        """Generate trading signals from sentiment analysis."""
        signals = []
        
        # Signal 1: Strong bullish sentiment with volume
        if metrics.sentiment_avg > 30 and metrics.mentions_count > self.min_mentions_threshold * 2:
            signals.append(SentimentSignal(
                symbol=symbol,
                sentiment_score=metrics.sentiment_avg,
                confidence=aggregated.get('confidence', 0.7),
                sources=['twitter', 'reddit', 'news'],
                signal_type='bullish',
                strength=min(100, metrics.sentiment_avg),
                timestamp=datetime.now(),
                keywords=['bullish', 'moon', 'buy'],
                volume_spike=True
            ))
        
        # Signal 2: Influencer accumulation
        if metrics.influencer_sentiment > 40 and metrics.smart_money_sentiment > 30:
            signals.append(SentimentSignal(
                symbol=symbol,
                sentiment_score=metrics.influencer_sentiment,
                confidence=0.85,
                sources=['twitter_influencers'],
                signal_type='bullish',
                strength=80,
                timestamp=datetime.now(),
                keywords=['accumulation', 'smart_money'],
                volume_spike=False
            ))
        
        # Signal 3: FUD detection
        if metrics.fud_index > 50:
            signals.append(SentimentSignal(
                symbol=symbol,
                sentiment_score=-metrics.fud_index,
                confidence=0.75,
                sources=['twitter', 'reddit'],
                signal_type='bearish',
                strength=metrics.fud_index,
                timestamp=datetime.now(),
                keywords=['fud', 'sell', 'dump'],
                volume_spike=True
            ))
        
        # Signal 4: FOMO warning
        if metrics.fomo_index > 70:
            signals.append(SentimentSignal(
                symbol=symbol,
                sentiment_score=metrics.fomo_index,
                confidence=0.7,
                sources=['twitter', 'reddit'],
                signal_type='bearish',  # FOMO often indicates top
                strength=50,
                timestamp=datetime.now(),
                keywords=['fomo', 'overbought'],
                volume_spike=True
            ))
        
        return signals
    
    async def _get_ai_insights(self, symbol: str, aggregated: Dict, 
                              metrics: SocialMetrics) -> Dict:
        """Get AI-powered insights using GPT."""
        try:
            prompt = f"""
            Analyze the following crypto sentiment data for {symbol}:
            
            Overall Sentiment: {aggregated.get('score', 0):.1f} ({aggregated.get('mood', 'Neutral')})
            Mentions: {metrics.mentions_count}
            Influencer Sentiment: {metrics.influencer_sentiment:.1f}
            Retail Sentiment: {metrics.retail_sentiment:.1f}
            FOMO Index: {metrics.fomo_index:.1f}
            FUD Index: {metrics.fud_index:.1f}
            
            Provide:
            1. Market sentiment interpretation
            2. Likely price direction (1-24 hours)
            3. Key risks to watch
            4. Recommended action (buy/sell/hold)
            
            Be concise and data-driven.
            """
            
            # Use OpenAI API
            response = await openai.ChatCompletion.acreate(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are a crypto market analyst expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=200
            )
            
            ai_analysis = response.choices[0].message.content
            
            return {
                "analysis": ai_analysis,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"AI insights error: {e}")
            return {
                "analysis": "AI analysis unavailable",
                "error": str(e)
            }
    
    def _extract_keywords(self, tweets: List[Dict]) -> List[str]:
        """Extract trending keywords from tweets."""
        # Simplified keyword extraction
        all_text = ' '.join([t.get('text', '') for t in tweets])
        words = re.findall(r'\b\w+\b', all_text.lower())
        
        # Count frequencies
        word_freq = {}
        for word in words:
            if len(word) > 3 and word not in ['the', 'and', 'for', 'with']:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Get top keywords
        top_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        return [word for word, _ in top_keywords]
    
    def store_sentiment_history(self, symbol: str, sentiment_data: Dict):
        """Store sentiment history for trend analysis."""
        if symbol not in self.sentiment_history:
            self.sentiment_history[symbol] = deque(maxlen=1000)
            
        self.sentiment_history[symbol].append({
            'timestamp': datetime.now(),
            'sentiment': sentiment_data.get('overall_sentiment', {}).get('score', 0),
            'mentions': sentiment_data.get('social_metrics', {}).get('mentions_count', 0)
        })
    
    def get_sentiment_trend(self, symbol: str, hours: int = 24) -> Dict:
        """Get sentiment trend over specified hours."""
        if symbol not in self.sentiment_history:
            return {}
            
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_data = [
            d for d in self.sentiment_history[symbol]
            if d['timestamp'] > cutoff_time
        ]
        
        if not recent_data:
            return {}
            
        sentiments = [d['sentiment'] for d in recent_data]
        mentions = [d['mentions'] for d in recent_data]
        
        return {
            "trend_direction": "up" if sentiments[-1] > sentiments[0] else "down",
            "sentiment_change": sentiments[-1] - sentiments[0],
            "avg_sentiment": np.mean(sentiments),
            "sentiment_volatility": np.std(sentiments),
            "mention_trend": "increasing" if mentions[-1] > mentions[0] else "decreasing",
            "data_points": len(recent_data)
        }
