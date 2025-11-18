#!/usr/bin/env python3
"""
Automatyczny Bot Tradingowy - Start
Uruchom ten plik aby rozpocząć automatyczne tradowanie
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Załaduj zmienne środowiskowe
load_dotenv()

# Dodaj projekt do ścieżki
sys.path.append(str(Path(__file__).parent))

def check_config():
    """Sprawdź czy konfiguracja jest ustawiona"""
    required_vars = [
        "EXCHANGE_API_KEY",
        "EXCHANGE_API_SECRET", 
        "OPENAI_API_KEY"
    ]
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        print("❌ BŁĄD: Brakuje wymaganych zmiennych środowiskowych:")
        for var in missing:
            print(f"   - {var}")
        print("\n📝 Instrukcje:")
        print("1. Skopiuj plik .env.example do .env")
        print("2. Wypełnij wszystkie wymagane wartości")
        print("3. Uruchom ponownie bota")
        sys.exit(1)

def main():
    """Główna funkcja uruchamiająca bota"""
    print("""
    ╔══════════════════════════════════════════╗
    ║     AUTOMATYCZNY BOT TRADINGOWY v1.0     ║
    ╠══════════════════════════════════════════╣
    ║  ⚡ Powered by AI (GPT-5 Pro)            ║
    ║  📊 Multi-Strategy Trading               ║
    ║  🔒 Advanced Risk Management             ║
    ╚══════════════════════════════════════════╝
    """)
    
    # Sprawdź konfigurację
    print("🔍 Sprawdzanie konfiguracji...")
    check_config()
    print("✅ Konfiguracja OK\n")
    
    # Import i uruchomienie bota
    print("🚀 Uruchamianie bota...")
    print("⚠️  Aby zatrzymać bota, naciśnij Ctrl+C\n")
    
    try:
        from bot.auto_trader import main as run_bot
        import asyncio
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n\n👋 Bot został zatrzymany przez użytkownika")
    except Exception as e:
        print(f"\n❌ Błąd krytyczny: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
