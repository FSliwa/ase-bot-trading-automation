#!/usr/bin/env python3
"""
OpenAI GPT-5 Web Search Tool for Market Analysis
Dodaje funkcjonalność głębokiego przeszukiwania internetu z wykorzystaniem OpenAI API
"""

import json
import requests
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import re
from bot.db import DatabaseManager

class WebSearchTool:
    """Tool do przeszukiwania internetu z AI analysis"""
    
    def __init__(self, openai_client_class):
        # Store the client class instead of instance
        self.openai_client_class = openai_client_class
        self.search_engines = {
            'google': 'https://www.googleapis.com/customsearch/v1',
            'bing': 'https://api.bing.microsoft.com/v7.0/search',
            'duckduckgo': 'https://api.duckduckgo.com'
        }
        
    def deep_market_search(self, query: str, symbol: str = None) -> Dict[str, Any]:
        """Wykonuje głębokie przeszukiwanie rynku dla danego symbolu"""
        
        # Konstruuj zapytania wyszukiwania
        search_queries = self._build_search_queries(query, symbol)
        
        # Przeszukaj internet
        search_results = self._perform_searches(search_queries)
        
        # Analizuj treści stron
        analyzed_content = self._analyze_web_content(search_results)
        
        # Zapisz dane do bazy (research + wskaźniki)
        self._persist_research_and_indicators(analyzed_content, query, symbol)

        # Generuj AI-powered analysis
        ai_analysis = self._generate_ai_analysis(analyzed_content, query, symbol)
        
        return {
            'success': True,
            'symbol': symbol,
            'query': query,
            'search_results_count': len(search_results),
            'analyzed_pages': len(analyzed_content),
            'ai_analysis': ai_analysis,
            'sources': [result['url'] for result in search_results[:10]],
            'timestamp': datetime.now().isoformat()
        }

    def _sentiment_to_score(self, label: str) -> float:
        m = {
            'Positive': 0.7,
            'Neutral': 0.0,
            'Negative': -0.7,
        }
        return m.get(label, 0.0)

    def _persist_research_and_indicators(self, analyzed_content: List[Dict[str, Any]], query: str, symbol: Optional[str]):
        if not analyzed_content:
            return
        try:
            with DatabaseManager() as db:
                scores: List[float] = []
                for item in analyzed_content:
                    score = self._sentiment_to_score(item.get('sentiment'))
                    scores.append(score)
                    db.save_research_article(
                        source=item.get('source') or 'unknown',
                        source_url=item.get('url'),
                        title=item.get('title'),
                        summary=item.get('content_summary'),
                        topic='market',
                        symbol=symbol,
                        published_at=None,
                        sentiment_score=score,
                        relevance=float(item.get('relevance_score') or 0.0),
                        credibility=0.5,
                        raw_json=json.dumps(item),
                        features_json=json.dumps({
                            'query': query,
                            'key_points': item.get('key_points', []),
                        })
                    )
                # Zapisz wskaźnik zbiorczy sentimentu jako WebIndicatorSnapshot
                if scores:
                    avg_sent = sum(scores) / max(1, len(scores))
                    db.save_web_indicator(
                        indicator='news_sentiment',
                        symbol=symbol,
                        value=avg_sent,
                        source='web_search_tool',
                        horizon_s=3600,
                        meta=json.dumps({'query': query, 'items': len(scores)})
                    )
        except Exception as e:
            # Nie przerywaj całego flow – loguj w stdout
            print(f"DB persist error: {e}")
    
    def _build_search_queries(self, query: str, symbol: str = None) -> List[str]:
        """Tworzy zoptymalizowane zapytania wyszukiwania"""
        
        base_queries = [
            f"{query}",
            f"{symbol} price analysis" if symbol else "crypto market analysis",
            f"{symbol} technical analysis today" if symbol else "cryptocurrency technical analysis",
            f"{symbol} news latest" if symbol else "crypto market news",
            f"{symbol} trading signals" if symbol else "crypto trading signals",
            f"{symbol} market sentiment" if symbol else "crypto market sentiment"
        ]
        
        # Dodaj specjalistyczne zapytania
        specialized_queries = [
            f"{symbol} whale movements" if symbol else "crypto whale activity",
            f"{symbol} volume analysis" if symbol else "crypto volume analysis",
            f"{symbol} support resistance levels" if symbol else "crypto support resistance",
            f"{symbol} institutional adoption" if symbol else "crypto institutional news",
            f"{symbol} regulatory news" if symbol else "crypto regulation news"
        ]
        
        return base_queries + specialized_queries
    
    def _perform_searches(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Wykonuje przeszukiwanie internetu"""
        
        all_results = []
        
        for query in queries[:5]:  # Limituj do 5 zapytań
            try:
                # Symulacja wyszukiwania (w rzeczywistości użyłbyś API Google/Bing)
                results = self._simulate_search(query)
                all_results.extend(results)
            except Exception as e:
                print(f"Search error for '{query}': {e}")
                continue
        
        # Usuń duplikaty na podstawie URL
        unique_results = []
        seen_urls = set()
        
        for result in all_results:
            if result['url'] not in seen_urls:
                unique_results.append(result)
                seen_urls.add(result['url'])
        
        return unique_results[:20]  # Maksymalnie 20 wyników
    
    def _simulate_search(self, query: str) -> List[Dict[str, Any]]:
        """Symuluje wyniki wyszukiwania (zastąp rzeczywistym API)"""
        
        # W rzeczywistej implementacji użyłbyś Google Search API lub Bing API
        mock_results = [
            {
                'title': f"Market Analysis: {query}",
                'url': f"https://coindesk.com/analysis/{query.replace(' ', '-')}",
                'snippet': f"Latest analysis on {query} shows significant market movements...",
                'source': 'CoinDesk'
            },
            {
                'title': f"Trading Signals: {query}",
                'url': f"https://cryptoslate.com/signals/{query.replace(' ', '-')}",
                'snippet': f"Professional trading signals for {query} indicate...",
                'source': 'CryptoSlate'
            },
            {
                'title': f"Technical Analysis: {query}",
                'url': f"https://tradingview.com/analysis/{query.replace(' ', '-')}",
                'snippet': f"Comprehensive technical analysis of {query} reveals...",
                'source': 'TradingView'
            }
        ]
        
        return mock_results
    
    def _analyze_web_content(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analizuje treść pobranych stron internetowych"""
        
        analyzed_content = []
        
        for result in search_results[:10]:  # Analizuj maksymalnie 10 stron
            try:
                # Symulacja pobierania treści strony
                content = self._fetch_page_content(result['url'])
                
                if content:
                    analyzed = {
                        'url': result['url'],
                        'title': result['title'],
                        'source': result.get('source', 'Unknown'),
                        'content_summary': content[:500] + "...",
                        'key_points': self._extract_key_points(content),
                        'sentiment': self._analyze_sentiment(content),
                        'relevance_score': self._calculate_relevance(content, result['title'])
                    }
                    analyzed_content.append(analyzed)
                    
            except Exception as e:
                print(f"Content analysis error for {result['url']}: {e}")
                continue
        
        return analyzed_content
    
    def _fetch_page_content(self, url: str) -> Optional[str]:
        """Pobiera treść strony internetowej"""
        
        # Symulacja treści strony
        mock_content = f"""
        Market Analysis Report for {url}
        
        Current market conditions show significant volatility in cryptocurrency markets.
        Technical indicators suggest a potential reversal pattern forming.
        
        Key Metrics:
        - RSI: 45.2 (Neutral)
        - MACD: Bullish crossover
        - Volume: Above average
        - Support: $45,000
        - Resistance: $48,500
        
        Recent news and events have impacted market sentiment.
        Institutional adoption continues to grow.
        Regulatory clarity improves investor confidence.
        
        Trading Recommendation: 
        Conservative approach recommended with proper risk management.
        Monitor key support/resistance levels for breakout signals.
        """
        
        return mock_content
    
    def _extract_key_points(self, content: str) -> List[str]:
        """Wyciąga kluczowe punkty z treści"""
        
        # Proste wyciąganie kluczowych punktów
        lines = content.split('\n')
        key_points = []
        
        for line in lines:
            line = line.strip()
            if line and (
                'support' in line.lower() or 
                'resistance' in line.lower() or
                'rsi' in line.lower() or
                'macd' in line.lower() or
                'volume' in line.lower() or
                'recommendation' in line.lower()
            ):
                key_points.append(line)
        
        return key_points[:5]  # Maksymalnie 5 punktów
    
    def _analyze_sentiment(self, content: str) -> str:
        """Analizuje sentiment treści"""
        
        positive_words = ['bullish', 'positive', 'growth', 'increase', 'buy', 'strong']
        negative_words = ['bearish', 'negative', 'decline', 'decrease', 'sell', 'weak']
        
        content_lower = content.lower()
        
        positive_count = sum(1 for word in positive_words if word in content_lower)
        negative_count = sum(1 for word in negative_words if word in content_lower)
        
        if positive_count > negative_count:
            return 'Positive'
        elif negative_count > positive_count:
            return 'Negative'
        else:
            return 'Neutral'
    
    def _calculate_relevance(self, content: str, title: str) -> float:
        """Oblicza relevance score treści"""
        
        # Prosta metoda oceny relevance
        trading_keywords = ['price', 'analysis', 'trading', 'market', 'crypto', 'bitcoin', 'ethereum']
        
        content_lower = content.lower()
        title_lower = title.lower()
        
        relevance_score = 0.0
        
        for keyword in trading_keywords:
            if keyword in content_lower:
                relevance_score += 0.1
            if keyword in title_lower:
                relevance_score += 0.2
        
        return min(relevance_score, 1.0)  # Maksymalnie 1.0
    
    def _generate_ai_analysis(self, analyzed_content: List[Dict[str, Any]], 
                             original_query: str, symbol: str = None) -> str:
        """Generuje AI-powered analysis na podstawie zebranych danych"""
        
        # Przygotuj kontekst dla AI
        context = self._prepare_ai_context(analyzed_content, original_query, symbol)
        
        # Prompt dla AI
        ai_prompt = f"""
        Jako ekspert analizy rynku kryptowalut, przeanalizuj zebrane dane z internetu i udziel profesjonalnej opinii.

        ZAPYTANIE UŻYTKOWNIKA: {original_query}
        SYMBOL: {symbol if symbol else 'Ogólny rynek crypto'}

        ZEBRANE DANE Z INTERNETU:
        {context}

        Na podstawie tych danych, udziel:
        1. Kompleksowej analizy technicznej
        2. Oceny sentimentu rynku  
        3. Kluczowych poziomów wsparcia/oporu
        4. Rekomendacji tradingowej z zarządzaniem ryzykiem
        5. Prognozę krótko- i średnioterminową

        Odpowiedź powinna być konkretna, oparta na faktach i zawierać jasne rekomendacje.
        """
        
        try:
            # Używaj istniejącego OpenAI client class
            import os
            api_key = os.getenv('OPENAI_API_KEY')
            
            if not api_key:
                return "Błąd: Brak konfiguracji OpenAI API key"
            
            # Create instance of client
            openai_client = self.openai_client_class(api_key)
            
            # Use chat completion
            response = openai_client.chat_completion(
                messages=[{"role": "user", "content": ai_prompt}],
                model="gpt-4o",
                temperature=0.3
            )
            
            if "error" in response:
                return f"Błąd AI analysis: {response['error']['message']}"
            else:
                return response["choices"][0]["message"]["content"]
            
        except Exception as e:
            return f"Błąd AI analysis: {str(e)}"
    
    def _prepare_ai_context(self, analyzed_content: List[Dict[str, Any]], 
                           query: str, symbol: str) -> str:
        """Przygotowuje kontekst dla AI na podstawie analizowanych treści"""
        
        context_parts = []
        
        for i, content in enumerate(analyzed_content[:5], 1):
            context_part = f"""
            ŹRÓDŁO {i}: {content['source']} - {content['title']}
            URL: {content['url']}
            SENTIMENT: {content['sentiment']}
            RELEVANCE: {content['relevance_score']:.2f}
            
            KLUCZOWE PUNKTY:
            {chr(10).join(f"- {point}" for point in content['key_points'])}
            
            STRESZCZENIE TREŚCI:
            {content['content_summary']}
            
            ---
            """
            context_parts.append(context_part)
        
        return '\n'.join(context_parts)


class WebSearchAPI:
    """API endpoint dla web search functionality"""
    
    def __init__(self, openai_client_class):
        # Store the client class instead of instance
        self.openai_client_class = openai_client_class
        self.web_search_tool = WebSearchTool(openai_client_class)
    
    def handle_web_search_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Obsługuje żądania web search"""
        
        try:
            query = request_data.get('query', '')
            symbol = request_data.get('symbol', None)
            
            if not query:
                return {
                    'success': False,
                    'error': 'Query is required'
                }
            
            # Wykonaj web search analysis
            result = self.web_search_tool.deep_market_search(query, symbol)
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Web search failed: {str(e)}'
            }


# Funkcja pomocnicza do integracji z istniejącym kodem
async def perform_web_enhanced_analysis(openai_client, query: str, symbol: str = None) -> Dict[str, Any]:
    """Funkcja pomocnicza do wykonywania web-enhanced analysis"""
    
    web_search_api = WebSearchAPI(openai_client)
    
    request_data = {
        'query': query,
        'symbol': symbol
    }
    
    result = await web_search_api.handle_web_search_request(request_data)
    
    return result


if __name__ == "__main__":
    print("🌐 Web Search Tool for Market Analysis")
    print("This tool provides deep internet search capabilities for crypto market analysis")
    print("Integration with OpenAI GPT-5/GPT-4o for intelligent content analysis")
