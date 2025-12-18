#!/usr/bin/env python3
"""
Test Gemini API Integration for Trading Bot
Sprawdza połączenie z Gemini API i wykonuje test analizy rynku
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_gemini_api():
    """Test podstawowej funkcjonalności Gemini API"""
    print("🚀 Testowanie Gemini API Integration...")
    
    # Check API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        print("❌ GEMINI_API_KEY nie jest ustawiony!")
        print("   Dodaj do .env:")
        print("   GEMINI_API_KEY=AIzaSy...")
        return False
    
    print(f"✅ Gemini API Key: {api_key[:10]}...{api_key[-4:]}")
    
    # Check model
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
    print(f"✅ Gemini Model: {model}")
    
    try:
        # Import Gemini client
        import google.generativeai as genai
        
        # Configure API
        genai.configure(api_key=api_key)
        
        # Initialize model
        model_instance = genai.GenerativeModel(model)
        
        print("✅ Gemini client initialized successfully")
        
        # Test simple query
        print("📡 Wysyłanie zapytania testowego do Gemini API...")
        
        test_prompt = """
        Jesteś ekspertem od analizy rynków finansowych. 
        Przeanalizuj obecną sytuację na rynku BTC/USDT.
        
        Odpowiedz w formacie JSON:
        {
            "symbol": "BTC/USDT",
            "sentiment": "bullish/bearish/neutral",
            "confidence": 0.0-1.0,
            "recommendation": "buy/sell/hold",
            "analysis": "krótka analiza"
        }
        """
        
        response = model_instance.generate_content(test_prompt)
        
        if response.text:
            print("✅ Gemini API odpowiedziało pomyślnie")
            print(f"📊 Odpowiedź: {response.text[:200]}...")
            
            # Try to parse as JSON
            try:
                # Extract JSON from response
                text = response.text.strip()
                if text.startswith('```json'):
                    text = text[7:]
                if text.endswith('```'):
                    text = text[:-3]
                
                json_data = json.loads(text)
                print("✅ Odpowiedź jest poprawnym JSON")
                print(f"   Symbol: {json_data.get('symbol', 'N/A')}")
                print(f"   Sentiment: {json_data.get('sentiment', 'N/A')}")
                print(f"   Rekomendacja: {json_data.get('recommendation', 'N/A')}")
                
            except json.JSONDecodeError:
                print("⚠️ Odpowiedź nie jest JSON, ale API działa")
            
            return True
        else:
            print("❌ Gemini API nie zwróciło odpowiedzi")
            return False
            
    except ImportError:
        print("❌ Brak biblioteki google-generativeai")
        print("   Zainstaluj: pip install google-generativeai")
        return False
        
    except Exception as e:
        print(f"❌ Błąd Gemini API: {e}")
        return False

def test_gemini_in_app():
    """Test integracji Gemini w aplikacji"""
    print("\n🔧 Testowanie integracji w aplikacji...")
    
    try:
        # Add current directory to path
        sys.path.insert(0, str(Path(__file__).parent))
        
        # Test import of Gemini analyzer
        from bot.gemini_analysis import get_gemini_analyzer
        
        analyzer = get_gemini_analyzer()
        if analyzer:
            print("✅ Gemini analyzer zainicjalizowany w aplikacji")
            return True
        else:
            print("❌ Nie udało się zainicjalizować Gemini analyzer")
            return False
            
    except ImportError as e:
        print(f"❌ Błąd importu: {e}")
        return False
    except Exception as e:
        print(f"❌ Błąd inicjalizacji: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Gemini API Test Suite")
    print("=" * 50)
    
    success_count = 0
    total_tests = 2
    
    # Test 1: Basic API
    if test_gemini_api():
        success_count += 1
        print("✅ Test 1: Gemini API - PASSED")
    else:
        print("❌ Test 1: Gemini API - FAILED")
    
    print()
    
    # Test 2: App Integration
    if test_gemini_in_app():
        success_count += 1
        print("✅ Test 2: App Integration - PASSED")
    else:
        print("❌ Test 2: App Integration - FAILED")
    
    print("\n" + "=" * 50)
    print(f"📊 Wyniki: {success_count}/{total_tests} testów PASSED")
    
    if success_count == total_tests:
        print("🎉 Wszystkie testy PASSED! Gemini API działa poprawnie.")
        print("\n🚀 System jest gotowy do pracy z Gemini AI!")
        return True
    else:
        print(f"⚠️ {total_tests - success_count} testów FAILED")
        print("\n🔧 Sprawdź konfigurację:")
        print("1. 🔑 Ustaw poprawny GEMINI_API_KEY w pliku .env")
        print("2. 🌐 Sprawdź połączenie internetowe")
        print("3. 💳 Sprawdź czy masz kredyty na koncie Google AI")
        print("4. 📦 Zainstaluj: pip install google-generativeai")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
