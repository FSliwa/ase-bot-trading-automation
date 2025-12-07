"""
Tavily Web Search Integration for ASE Trading Bot
Real-time market intelligence and news aggregation
"""

import os
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import json

logger = logging.getLogger(__name__)

class SearchDepth(Enum):
    """Search depth options for Tavily API"""
    BASIC = "basic"
    ADVANCED = "advanced"

@dataclass
class SearchResult:
    """Structured search result from Tavily API"""
    title: str
    url: str
    content: str
    score: float
    published_date: Optional[datetime] = None
    source_domain: str = ""
    
class TavilyWebSearch:
    """
    Tavily Web Search API client for market intelligence
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('TAVILY_API_KEY')
        self.base_url = "https://api.tavily.com"
        self.max_results = int(os.getenv('TAVILY_MAX_RESULTS', 10))
        self.search_depth = os.getenv('TAVILY_SEARCH_DEPTH', 'basic')
        self.include_domains = os.getenv('TAVILY_INCLUDE_DOMAINS', '').split(',') if os.getenv('TAVILY_INCLUDE_DOMAINS') else []
        self.exclude_domains = os.getenv('TAVILY_EXCLUDE_DOMAINS', '').split(',') if os.getenv('TAVILY_EXCLUDE_DOMAINS') else []
        
        if not self.api_key:
            raise ValueError("Tavily API key is required. Set TAVILY_API_KEY environment variable.")
    
    async def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        search_depth: Optional[SearchDepth] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        include_raw_content: bool = False,
        include_images: bool = False
    ) -> List[SearchResult]:
        """
        Perform web search using Tavily API
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return
            search_depth: Search depth (basic or advanced)
            include_domains: List of domains to include
            exclude_domains: List of domains to exclude
            include_raw_content: Include raw HTML content
            include_images: Include image results
            
        Returns:
            List of SearchResult objects
        """
        try:
            payload = {
                "api_key": self.api_key,
                "query": query,
                "max_results": max_results or self.max_results,
                "search_depth": (search_depth or SearchDepth.BASIC).value,
                "include_raw_content": include_raw_content,
                "include_images": include_images
            }
            
            # Add domain filters if provided
            if include_domains or self.include_domains:
                payload["include_domains"] = include_domains or self.include_domains
            
            if exclude_domains or self.exclude_domains:
                payload["exclude_domains"] = exclude_domains or self.exclude_domains
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/search",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Tavily API error {response.status}: {error_text}")
                        return []
                    
                    data = await response.json()
                    return self._parse_results(data.get('results', []))
                    
        except Exception as e:
            logger.error(f"Error performing Tavily search: {str(e)}")
            return []
    
    def _parse_results(self, raw_results: List[Dict[str, Any]]) -> List[SearchResult]:
        """Parse raw API results into SearchResult objects"""
        results = []
        
        for item in raw_results:
            try:
                # Extract domain from URL
                from urllib.parse import urlparse
                parsed_url = urlparse(item.get('url', ''))
                source_domain = parsed_url.netloc
                
                # Try to parse published date if available
                published_date = None
                if 'published_date' in item and item['published_date']:
                    try:
                        published_date = datetime.fromisoformat(item['published_date'].replace('Z', '+00:00'))
                    except:
                        pass
                
                result = SearchResult(
                    title=item.get('title', ''),
                    url=item.get('url', ''),
                    content=item.get('content', ''),
                    score=float(item.get('score', 0.0)),
                    published_date=published_date,
                    source_domain=source_domain
                )
                results.append(result)
                
            except Exception as e:
                logger.warning(f"Error parsing search result: {str(e)}")
                continue
        
        return results
    
    async def search_crypto_news(
        self,
        symbol: str = "",
        timeframe: str = "24h",
        max_results: int = 20
    ) -> List[SearchResult]:
        """
        Search for cryptocurrency news
        
        Args:
            symbol: Crypto symbol (e.g., "BTC", "ETH")
            timeframe: Time window for news (24h, 7d, 30d)
            max_results: Maximum results to return
            
        Returns:
            List of SearchResult objects
        """
        # Build search query
        if symbol:
            query = f"{symbol} cryptocurrency news {timeframe}"
        else:
            query = f"cryptocurrency market news {timeframe}"
        
        # Use crypto-focused domains
        crypto_domains = [
            "coindesk.com",
            "cointelegraph.com",
            "cryptonews.com",
            "bitcoinmagazine.com",
            "decrypt.co",
            "coinmarketcap.com",
            "coingecko.com"
        ]
        
        return await self.search(
            query=query,
            max_results=max_results,
            search_depth=SearchDepth.ADVANCED,
            include_domains=crypto_domains
        )
    
    async def search_market_sentiment(
        self,
        symbols: List[str],
        max_results: int = 15
    ) -> Dict[str, List[SearchResult]]:
        """
        Search for market sentiment about specific cryptocurrencies
        
        Args:
            symbols: List of crypto symbols
            max_results: Maximum results per symbol
            
        Returns:
            Dictionary mapping symbols to search results
        """
        sentiment_results = {}
        
        for symbol in symbols:
            query = f"{symbol} price prediction analysis sentiment bull bear market"
            results = await self.search(
                query=query,
                max_results=max_results,
                search_depth=SearchDepth.ADVANCED
            )
            sentiment_results[symbol] = results
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)
        
        return sentiment_results
    
    async def search_trading_signals(
        self,
        symbol: str,
        strategy_type: str = "technical analysis"
    ) -> List[SearchResult]:
        """
        Search for trading signals and technical analysis
        
        Args:
            symbol: Crypto symbol
            strategy_type: Type of analysis to search for
            
        Returns:
            List of SearchResult objects
        """
        query = f"{symbol} {strategy_type} trading signals buy sell indicators"
        
        return await self.search(
            query=query,
            max_results=10,
            search_depth=SearchDepth.ADVANCED,
            include_domains=[
                "tradingview.com",
                "coindesk.com",
                "cryptoslate.com",
                "ambcrypto.com"
            ]
        )
    
    async def search_regulatory_news(self, max_results: int = 10) -> List[SearchResult]:
        """
        Search for cryptocurrency regulatory news
        
        Args:
            max_results: Maximum results to return
            
        Returns:
            List of SearchResult objects
        """
        query = "cryptocurrency regulation SEC Bitcoin ETF legal news"
        
        return await self.search(
            query=query,
            max_results=max_results,
            search_depth=SearchDepth.ADVANCED,
            include_domains=[
                "coindesk.com",
                "cointelegraph.com",
                "reuters.com",
                "bloomberg.com",
                "sec.gov"
            ]
        )
    
    async def batch_search(
        self,
        queries: List[str],
        max_results_per_query: int = 5,
        delay_between_requests: float = 1.0
    ) -> Dict[str, List[SearchResult]]:
        """
        Perform multiple searches with rate limiting
        
        Args:
            queries: List of search queries
            max_results_per_query: Max results per query
            delay_between_requests: Delay between requests in seconds
            
        Returns:
            Dictionary mapping queries to results
        """
        results = {}
        
        for query in queries:
            try:
                search_results = await self.search(
                    query=query,
                    max_results=max_results_per_query
                )
                results[query] = search_results
                
                # Rate limiting delay
                if delay_between_requests > 0:
                    await asyncio.sleep(delay_between_requests)
                    
            except Exception as e:
                logger.error(f"Error in batch search for query '{query}': {str(e)}")
                results[query] = []
        
        return results
    
    def format_results_for_ai(self, results: List[SearchResult]) -> str:
        """
        Format search results for AI consumption
        
        Args:
            results: List of SearchResult objects
            
        Returns:
            Formatted string suitable for AI analysis
        """
        if not results:
            return "No search results found."
        
        formatted_results = []
        for i, result in enumerate(results[:10], 1):  # Limit to top 10 results
            date_str = result.published_date.strftime("%Y-%m-%d") if result.published_date else "Unknown date"
            
            formatted_result = f"""
{i}. {result.title}
   Source: {result.source_domain}
   Date: {date_str}
   Score: {result.score:.2f}
   Content: {result.content[:300]}{'...' if len(result.content) > 300 else ''}
   URL: {result.url}
"""
            formatted_results.append(formatted_result)
        
        return "\n".join(formatted_results)
    
    async def get_market_intelligence_summary(
        self,
        symbols: Optional[List[str]] = None,
        include_sentiment: bool = True,
        include_regulatory: bool = True
    ) -> Dict[str, Any]:
        """
        Get comprehensive market intelligence summary
        
        Args:
            symbols: List of crypto symbols to analyze
            include_sentiment: Include sentiment analysis
            include_regulatory: Include regulatory news
            
        Returns:
            Dictionary with comprehensive market intelligence
        """
        symbols = symbols or ["BTC", "ETH"]
        intelligence = {
            "timestamp": datetime.now().isoformat(),
            "symbols_analyzed": symbols,
            "news_summary": {},
            "sentiment_analysis": {},
            "regulatory_updates": [],
            "trading_signals": {}
        }
        
        try:
            # Get general crypto news
            general_news = await self.search_crypto_news(max_results=15)
            intelligence["news_summary"]["general"] = [
                {
                    "title": r.title,
                    "content": r.content[:200] + "...",
                    "url": r.url,
                    "source": r.source_domain,
                    "score": r.score
                } for r in general_news[:10]
            ]
            
            # Get symbol-specific news and sentiment
            for symbol in symbols:
                # Symbol news
                symbol_news = await self.search_crypto_news(symbol=symbol, max_results=10)
                intelligence["news_summary"][symbol] = [
                    {
                        "title": r.title,
                        "content": r.content[:200] + "...",
                        "url": r.url,
                        "source": r.source_domain,
                        "score": r.score
                    } for r in symbol_news[:5]
                ]
                
                # Trading signals
                signals = await self.search_trading_signals(symbol)
                intelligence["trading_signals"][symbol] = [
                    {
                        "title": r.title,
                        "content": r.content[:150] + "...",
                        "url": r.url,
                        "source": r.source_domain
                    } for r in signals[:3]
                ]
                
                await asyncio.sleep(1)  # Rate limiting
            
            # Sentiment analysis
            if include_sentiment and symbols:
                sentiment_results = await self.search_market_sentiment(symbols, max_results=5)
                intelligence["sentiment_analysis"] = {
                    symbol: [
                        {
                            "title": r.title,
                            "content": r.content[:150] + "...",
                            "url": r.url,
                            "source": r.source_domain
                        } for r in results[:3]
                    ] for symbol, results in sentiment_results.items()
                }
            
            # Regulatory updates
            if include_regulatory:
                regulatory_news = await self.search_regulatory_news(max_results=5)
                intelligence["regulatory_updates"] = [
                    {
                        "title": r.title,
                        "content": r.content[:200] + "...",
                        "url": r.url,
                        "source": r.source_domain,
                        "score": r.score
                    } for r in regulatory_news
                ]
            
        except Exception as e:
            logger.error(f"Error generating market intelligence summary: {str(e)}")
            intelligence["error"] = str(e)
        
        return intelligence

# Convenience functions
async def search_crypto_news(query: str, max_results: int = 10) -> List[SearchResult]:
    """Convenience function for quick crypto news search"""
    tavily = TavilyWebSearch()
    return await tavily.search_crypto_news(symbol=query, max_results=max_results)

async def get_market_intelligence(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """Convenience function for market intelligence"""
    tavily = TavilyWebSearch()
    return await tavily.get_market_intelligence_summary(symbols=symbols)

# Example usage
if __name__ == "__main__":
    async def main():
        # Initialize Tavily client
        tavily = TavilyWebSearch()
        
        # Test basic search
        print("Testing basic search...")
        results = await tavily.search("Bitcoin price prediction 2025")
        for result in results[:3]:
            print(f"Title: {result.title}")
            print(f"Source: {result.source_domain}")
            print(f"Content: {result.content[:100]}...")
            print("---")
        
        # Test crypto news search
        print("\nTesting crypto news search...")
        news = await tavily.search_crypto_news("BTC", max_results=5)
        for article in news:
            print(f"News: {article.title}")
            print(f"Source: {article.source_domain}")
            print("---")
        
        # Test market intelligence
        print("\nTesting market intelligence...")
        intelligence = await tavily.get_market_intelligence_summary(["BTC", "ETH"])
        print(f"Intelligence gathered for: {intelligence['symbols_analyzed']}")
        print(f"General news articles: {len(intelligence['news_summary']['general'])}")
    
    # Run example
    asyncio.run(main())
