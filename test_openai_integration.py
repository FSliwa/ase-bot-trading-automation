"""
Test OpenAI API Integration for Trading Bot
Sprawdza połączenie z API OpenAI i wykonuje test analizy rynku oraz decyzji handlowych
"""

import os
import asyncio
import json
from datetime import datetime
from typing import Dict, List
import sys
from pathlib import Path

# Dodaj path do modułów bota
sys.path.append(str(Path(__file__).parent.parent))

from bot.ai_analysis import MarketAnalyzer
from dotenv import load_dotenv

class OpenAITradingTest:
    """Test integracji OpenAI API z systemem tradingowym"""
    
    def __init__(self):
        load_dotenv()
        self.test_results = []
        
    def check_environment(self):
        """Sprawdź konfigurację środowiska"""
        print("🔍 Sprawdzanie konfiguracji środowiska...")
        
        # Sprawdź klucz API
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your_openai_api_key_here":
            print("❌ OPENAI_API_KEY nie jest ustawiony!")
            print("   Ustaw klucz API w pliku .env:")
            print("   OPENAI_API_KEY=sk-...")
            return False
            
        # Sprawdź model
        model = os.getenv("OPENAI_MODEL", "gpt-5")
        print(f"✅ OpenAI Model: {model}")
        
        # Sprawdź inne ustawienia
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url:
            print(f"✅ Custom Base URL: {base_url}")
        
        organization = os.getenv("OPENAI_ORG")
        if organization:
            print(f"✅ Organization: {organization}")
            
        print(f"✅ API Key: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else '****'}")
        return True
    
    async def test_market_analysis(self):
        """Test analizy rynku przez AI"""
        print("\n📊 Test analizy rynku...")
        
        try:
            analyzer = MarketAnalyzer()
            
            # Przygotuj parametry testowe
            test_parameters = {
                "PrimeXBT": "PrimeXBT",
                "notional": "10000",
                "150x": "150",
                "max impact bps": "10",
                "Lmax": "150",
                "YYYY-MM-DD HH:MM TZ": datetime.now().strftime("%Y-%m-%d %H:%M UTC")
            }
            
            print("📡 Wysyłanie zapytania do OpenAI API...")
            result = await analyzer.analyze_market(test_parameters)
            
            if "error" in result:
                print(f"❌ Błąd analizy rynku: {result['error']}")
                return False
            
            print("✅ Analiza rynku zakończona pomyślnie!")
            print(f"📈 Znaleziono {len(result.get('candidates', []))} kandydatów do tradingu")
            
            # Wyświetl wyniki
            if result.get('market_regime'):
                regime = result['market_regime']
                print(f"🎯 Reżim rynku: {regime.get('trend', 'N/A')} | Wolności: {regime.get('volatility_state', 'N/A')}")
                
            if result.get('top_pick'):
                pick = result['top_pick']
                print(f"🥇 Top pick: {pick.get('symbol', 'N/A')} - {pick.get('why', 'N/A')}")
                
            self.test_results.append({
                "test": "market_analysis",
                "status": "success",
                "data": result
            })
            
            return True
            
        except Exception as e:
            print(f"❌ Błąd podczas analizy rynku: {str(e)}")
            self.test_results.append({
                "test": "market_analysis",
                "status": "error",
                "error": str(e)
            })
            return False
    
    async def test_trade_execution_analysis(self):
        """Test analizy wykonania transakcji"""
        print("\n🎯 Test analizy wykonania transakcji...")
        
        try:
            analyzer = MarketAnalyzer()
            
            # Przygotuj parametry testowe dla konkretnej transakcji
            test_parameters = {
                "PrimeXBT/inna": "PrimeXBT",
                "1.0": "1.0",
                "5.0": "5.0",
                "1": "1",
                "10000": "10000",
                "150": "150",
                "500k": "500000",
                "5": "5",
                "1M": "1000000",
                "7": "7",
                "2": "2",
                "8": "8",
                "limit_post_only|market|twap": "limit_post_only",
                "10": "10",
                "GTC|IOC|FOK": "GTC",
                "isolated|cross": "isolated",
                "paper|live": "paper",
                "true|false": "true",
                "false": "false",
                "UTC": "UTC",
                "YYYY-MM-DD HH:MM": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "0.55": "0.55"
            }
            
            print("📡 Testowanie analizy transakcji BTC/USDT LONG...")
            result = await analyzer.analyze_trade_execution("BTC/USDT", "long", test_parameters)
            
            if "error" in result:
                print(f"❌ Błąd analizy transakcji: {result['error']}")
                return False
                
            print("✅ Analiza transakcji zakończona pomyślnie!")
            
            # Wyświetl kluczowe informacje
            if result.get('action'):
                print(f"🎯 Akcja: {result['action']}")
                
            if result.get('position_size'):
                print(f"💰 Wielkość pozycji: {result['position_size']}")
                
            if result.get('risk_assessment'):
                print(f"⚠️ Ocena ryzyka: {result['risk_assessment']}")
                
            self.test_results.append({
                "test": "trade_execution",
                "status": "success",
                "data": result
            })
            
            return True
            
        except Exception as e:
            print(f"❌ Błąd podczas analizy transakcji: {str(e)}")
            self.test_results.append({
                "test": "trade_execution",
                "status": "error",
                "error": str(e)
            })
            return False
    
    def test_ai_trading_integration(self):
        """Test integracji AI z systemem tradingowym"""
        print("\n🤖 Test integracji AI-Trading...")
        
        # Sprawdź dostępność modułów
        try:
            from web.app import app
            print("✅ Moduł web.app dostępny")
        except ImportError as e:
            print(f"❌ Błąd importu web.app: {e}")
            
        try:
            from bot.auto_trader import AutoTrader
            print("✅ Moduł AutoTrader dostępny")
        except ImportError as e:
            print(f"⚠️ AutoTrader niedostępny: {e}")
            
        # Sprawdź dostępność promptów
        prompts_dir = Path(__file__).parent.parent / "bot" / "prompts"
        if prompts_dir.exists():
            print(f"✅ Katalog promptów: {prompts_dir}")
            prompts = list(prompts_dir.glob("*.txt"))
            print(f"📝 Znaleziono {len(prompts)} promptów: {[p.name for p in prompts]}")
        else:
            print("❌ Katalog promptów nie istnieje")
            
        return True
    
    async def run_comprehensive_test(self):
        """Uruchom pełny test systemu"""
        print("🚀 Uruchamianie testów OpenAI API Integration...")
        print("=" * 60)
        
        # 1. Sprawdź środowisko
        if not self.check_environment():
            print("\n❌ Test przerwany - błędna konfiguracja")
            return False
            
        # 2. Test integracji modułów
        self.test_ai_trading_integration()
        
        # 3. Test analizy rynku
        success_market = await self.test_market_analysis()
        
        # 4. Test analizy transakcji
        success_trade = await self.test_trade_execution_analysis()
        
        # 5. Podsumowanie
        print("\n" + "=" * 60)
        print("📋 PODSUMOWANIE TESTÓW:")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        successful_tests = len([r for r in self.test_results if r["status"] == "success"])
        
        print(f"📊 Wykonano: {total_tests} testów")
        print(f"✅ Udane: {successful_tests}")
        print(f"❌ Nieudane: {total_tests - successful_tests}")
        
        if successful_tests == total_tests and total_tests > 0:
            print("\n🎉 Wszystkie testy PASSED! OpenAI API działa poprawnie.")
            return True
        else:
            print("\n⚠️ Niektóre testy FAILED. Sprawdź konfigurację.")
            return False
    
    def save_test_results(self):
        """Zapisz wyniki testów do pliku"""
        results_file = Path(__file__).parent / "openai_test_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "tests": self.test_results
            }, f, indent=2, ensure_ascii=False)
        print(f"💾 Wyniki zapisane do: {results_file}")

async def main():
    """Główna funkcja testowa"""
    tester = OpenAITradingTest()
    
    try:
        success = await tester.run_comprehensive_test()
        tester.save_test_results()
        
        if success:
            print("\n🎯 ZALECENIA:")
            print("1. ✅ API OpenAI jest skonfigurowane i działa")
            print("2. 🔄 Możesz używać AI do analizy rynku i decyzji handlowych")
            print("3. 📊 System jest gotowy do automatycznego tradingu z AI")
            print("4. ⚙️ Sprawdź dashboard w przeglądarce: http://localhost:8008")
        else:
            print("\n🛠️ ZALECENIA:")
            print("1. 🔑 Ustaw poprawny OPENAI_API_KEY w pliku .env")
            print("2. 🌐 Sprawdź połączenie internetowe")
            print("3. 💳 Sprawdź czy masz kredyty na koncie OpenAI")
            print("4. 📞 Skontaktuj się z OpenAI jeśli problem persystuje")
            
    except KeyboardInterrupt:
        print("\n⏹️ Test przerwany przez użytkownika")
    except Exception as e:
        print(f"\n💥 Nieoczekiwany błąd: {e}")

if __name__ == "__main__":
    asyncio.run(main())
