#!/usr/bin/env python3
"""
Test Gemini AI Integration for Trading Bot
Sprawdza połączenie z Gemini API i wykonuje test analizy rynku
"""

import os
import json
import asyncio
from pathlib import Path
from datetime import datetime

# Załaduj zmienne środowiskowe
from dotenv import load_dotenv
load_dotenv()

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ google-generativeai nie jest zainstalowane")


class GeminiTradingTest:
    """Test integracji Gemini API z systemem tradingowym"""
    
    def __init__(self):
        self.api_key = None
        self.model = None
        self.test_results = []
    
    def check_configuration(self):
        """Sprawdza konfigurację Gemini API"""
        print("🔧 Sprawdzanie konfiguracji Gemini API...")
        
        # Sprawdź dostępność biblioteki
        if not GEMINI_AVAILABLE:
            print("❌ Biblioteka google-generativeai nie jest zainstalowana!")
            print("   Zainstaluj: pip install google-generativeai")
            return False
        
        # Sprawdź klucz API
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key == "your_gemini_api_key_here":
            print("❌ GEMINI_API_KEY nie jest ustawiony!")
            print("   Dodaj do .env:")
            print("   GEMINI_API_KEY=AIzaSy...")
            return False
        
        self.api_key = api_key
        print(f"✅ Gemini API Key: {api_key[:10]}...{api_key[-4:]}")
        
        # Sprawdź model
        model = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
        print(f"✅ Gemini Model: {model}")
        self.model = model
        
        return True
    
    def initialize_client(self):
        """Inicjalizuje klienta Gemini"""
        try:
            print("🚀 Inicjalizacja klienta Gemini...")
            genai.configure(api_key=self.api_key)
            
            # Lista dostępnych modeli
            print("📋 Dostępne modele:")
            for model in genai.list_models():
                if 'generateContent' in model.supported_generation_methods:
                    print(f"   - {model.name}")
            
            return True
        except Exception as e:
            print(f"❌ Błąd inicjalizacji klienta: {e}")
            return False
    
    async def test_basic_connection(self):
        """Test podstawowego połączenia z Gemini API"""
        try:
            print("\n📡 Test podstawowego połączenia...")
            
            model = genai.GenerativeModel(self.model)
            
            prompt = "Odpowiedz krótko: Czy jesteś gotowy do analizy rynków finansowych?"
            
            response = model.generate_content(prompt)
            
            if response and response.text:
                print("✅ Połączenie z Gemini API działa!")
                print(f"📝 Odpowiedź: {response.text}")
                self.test_results.append({
                    "test": "basic_connection",
                    "status": "PASSED",
                    "response": response.text
                })
                return True
            else:
                print("❌ Brak odpowiedzi z API")
                return False
                
        except Exception as e:
            print(f"❌ Błąd połączenia: {e}")
            self.test_results.append({
                "test": "basic_connection",
                "status": "FAILED",
                "error": str(e)
            })
            return False
    
    async def test_market_analysis(self):
        """Test analizy rynku"""
        try:
            print("\n📊 Test analizy rynku...")
            
            model = genai.GenerativeModel(self.model)
            
            market_data = {
                "symbol": "BTC/USDT",
                "price": 65000,
                "volume_24h": 1500000000,
                "change_24h": 2.5,
                "rsi": 65,
                "moving_averages": {
                    "sma_20": 64500,
                    "sma_50": 63000,
                    "ema_12": 64800
                }
            }
            
            prompt = f"""
            Jako ekspert analizy technicznej, przeanalizuj następujące dane rynkowe dla {market_data['symbol']}:
            
            Cena: ${market_data['price']}
            Zmiana 24h: {market_data['change_24h']}%
            Volume 24h: ${market_data['volume_24h']:,}
            RSI: {market_data['rsi']}
            SMA 20: ${market_data['moving_averages']['sma_20']}
            SMA 50: ${market_data['moving_averages']['sma_50']}
            EMA 12: ${market_data['moving_averages']['ema_12']}
            
            Podaj krótką analizę i rekomendację handlową (BUY/SELL/HOLD) z uzasadnieniem.
            """
            
            response = model.generate_content(prompt)
            
            if response and response.text:
                print("✅ Analiza rynku wykonana pomyślnie!")
                print(f"📈 Analiza: {response.text[:200]}...")
                
                self.test_results.append({
                    "test": "market_analysis",
                    "status": "PASSED",
                    "symbol": market_data['symbol'],
                    "analysis": response.text
                })
                return True
            else:
                print("❌ Brak analizy z API")
                return False
                
        except Exception as e:
            print(f"❌ Błąd analizy: {e}")
            self.test_results.append({
                "test": "market_analysis",
                "status": "FAILED",
                "error": str(e)
            })
            return False
    
    async def test_trading_decision(self):
        """Test podejmowania decyzji handlowych"""
        try:
            print("\n🤖 Test decyzji handlowych...")
            
            model = genai.GenerativeModel(self.model)
            
            trading_scenario = {
                "portfolio_balance": 10000,
                "current_positions": [
                    {"symbol": "BTC/USDT", "size": 0.1, "entry_price": 64000, "pnl": 100}
                ],
                "market_trend": "bullish",
                "risk_tolerance": "medium"
            }
            
            prompt = f"""
            Jako AI trader, otrzymujesz następujące informacje:
            
            Saldo portfela: ${trading_scenario['portfolio_balance']}
            Aktualne pozycje: {trading_scenario['current_positions']}
            Trend rynku: {trading_scenario['market_trend']}
            Tolerancja ryzyka: {trading_scenario['risk_tolerance']}
            
            Podejmij decyzję handlową i zwróć odpowiedź w formacie JSON:
            {{
                "action": "BUY/SELL/HOLD",
                "symbol": "symbol",
                "size": "rozmiar pozycji",
                "stop_loss": "cena stop loss",
                "take_profit": "cena take profit",
                "reasoning": "uzasadnienie decyzji"
            }}
            """
            
            response = model.generate_content(prompt)
            
            if response and response.text:
                print("✅ Decyzja handlowa wygenerowana!")
                print(f"🎯 Decyzja: {response.text[:300]}...")
                
                self.test_results.append({
                    "test": "trading_decision",
                    "status": "PASSED",
                    "decision": response.text
                })
                return True
            else:
                print("❌ Brak decyzji z API")
                return False
                
        except Exception as e:
            print(f"❌ Błąd decyzji: {e}")
            self.test_results.append({
                "test": "trading_decision",
                "status": "FAILED",
                "error": str(e)
            })
            return False
    
    def save_results(self):
        """Zapisuje wyniki testów"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "gemini_model": self.model,
            "api_key_configured": bool(self.api_key),
            "tests": self.test_results
        }
        
        results_file = Path(__file__).parent / "gemini_test_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Wyniki zapisane do: {results_file}")


async def main():
    """Główna funkcja testowa"""
    print("🚀 Uruchamianie testów Gemini AI Integration...")
    print("=" * 60)
    
    tester = GeminiTradingTest()
    
    # Test 1: Konfiguracja
    if not tester.check_configuration():
        print("\n❌ Testy przerwane - błąd konfiguracji")
        return
    
    # Test 2: Inicjalizacja
    if not tester.initialize_client():
        print("\n❌ Testy przerwane - błąd inicjalizacji")
        return
    
    # Test 3: Podstawowe połączenie
    connection_ok = await tester.test_basic_connection()
    
    # Test 4: Analiza rynku (tylko jeśli połączenie działa)
    if connection_ok:
        await tester.test_market_analysis()
        await tester.test_trading_decision()
    
    # Podsumowanie
    print("\n" + "=" * 60)
    print("📊 PODSUMOWANIE TESTÓW")
    
    passed_tests = [t for t in tester.test_results if t["status"] == "PASSED"]
    failed_tests = [t for t in tester.test_results if t["status"] == "FAILED"]
    
    if len(passed_tests) == len(tester.test_results):
        print("\n🎉 Wszystkie testy PASSED! Gemini API działa poprawnie.")
        print("\n✅ System gotowy do użycia z Gemini AI!")
        print("✅ Możesz teraz uruchomić trading bota z AI")
    else:
        print(f"\n⚠️ Testy zakończone: {len(passed_tests)} PASSED, {len(failed_tests)} FAILED")
        if failed_tests:
            print("\n❌ Błędy:")
            for test in failed_tests:
                print(f"   - {test['test']}: {test.get('error', 'Unknown error')}")
    
    # Zapisz wyniki
    tester.save_results()
    
    # Wskazówki
    if connection_ok:
        print("\n💡 NASTĘPNE KROKI:")
        print("1. ✅ API Gemini jest skonfigurowane i działa")
        print("2. 🚀 Uruchom aplikację web: uvicorn web.app:app --host 0.0.0.0 --port 8008")
        print("3. 🌐 Otwórz dashboard: http://localhost:8008")
        print("4. 🤖 Przetestuj funkcje AI w panelu tradingowym")
    else:
        print("\n🔧 WYMAGANE DZIAŁANIA:")
        print("1. 🔑 Ustaw poprawny GEMINI_API_KEY w pliku .env")
        print("2. 📦 Zainstaluj: pip install google-generativeai")
        print("3. 💳 Sprawdź czy masz dostęp do Gemini API")
        print("4. 🔄 Uruchom test ponownie")


if __name__ == "__main__":
    asyncio.run(main())
