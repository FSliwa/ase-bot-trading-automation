"""
Script to add Binance API key for sky72199csgo@gmail.com user
"""
import sys
import os
sys.path.insert(0, 'Algorytm Uczenia Kwantowego LLM')

# Load environment variables FIRST
from dotenv import load_dotenv
load_dotenv('Algorytm Uczenia Kwantowego LLM/.env')

from sqlalchemy import create_engine, text
from bot.security import SecurityManager
from datetime import datetime, timezone
import uuid

# User details
USER_EMAIL = "sky72199csgo@gmail.com"
USER_ID = "47b49177-17e8-4426-a3f3-cfdafbf7b786"

# Binance API credentials
BINANCE_API_KEY = "pYTtnKM6qkM0BwyUAB4E3Pi8PDXhN5q9MGlOSoY8h7Z1rdCgWbGxhlFu96ZLCo0W"
BINANCE_SECRET = "FOLUmdfQc3lyMNiuCm4nOxJUl8TJZ1WCE65wGwqcB9t0tczSFKSHwtOQVKKIwDUi"

# Database connection
DATABASE_URL = "postgresql://postgres:MIlik112%21%404@db.iqqmbzznwpheqiihnjhz.supabase.co:5432/postgres"

print("="*70)
print("🔐 DODAWANIE KLUCZA API BINANCE")
print("="*70)
print(f"User: {USER_EMAIL}")
print(f"UUID: {USER_ID}")
print(f"Exchange: Binance")
print("="*70)

# Initialize security manager for encryption
sm = SecurityManager()

# Encrypt credentials
print("🔒 Szyfrowanie danych...")
print(f"🔑 Using ENCRYPTION_KEY: {os.getenv('ENCRYPTION_KEY', 'NOT SET')[:20]}...")
encrypted_key = sm.encrypt(BINANCE_API_KEY)
encrypted_secret = sm.encrypt(BINANCE_SECRET)
print("✅ Dane zaszyfrowane")

# Connect to database
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Check if API key already exists
    result = conn.execute(text("""
        SELECT id, is_active 
        FROM public.api_keys 
        WHERE user_id = :user_id AND exchange = 'binance'
    """), {"user_id": USER_ID})
    
    existing_key = result.fetchone()
    
    if existing_key:
        print(f"\n⚠️  Użytkownik ma już klucz API Binance (ID: {existing_key[0]})")
        print(f"   Status: {'aktywny' if existing_key[1] else 'nieaktywny'}")
        
        # Update existing key
        print("\n🔄 Aktualizuję istniejący klucz...")
        conn.execute(text("""
            UPDATE public.api_keys
            SET encrypted_api_key = :enc_key,
                encrypted_api_secret = :enc_secret,
                is_active = true,
                updated_at = :now
            WHERE user_id = :user_id AND exchange = 'binance'
        """), {
            "enc_key": encrypted_key,
            "enc_secret": encrypted_secret,
            "user_id": USER_ID,
            "now": datetime.now(timezone.utc)
        })
        conn.commit()
        print("✅ Klucz zaktualizowany")
        
    else:
        # Insert new key
        print("\n➕ Dodaję nowy klucz API...")
        api_key_id = str(uuid.uuid4())
        
        conn.execute(text("""
            INSERT INTO public.api_keys (
                id, user_id, exchange, encrypted_api_key, encrypted_api_secret, 
                is_active, created_at, updated_at
            )
            VALUES (
                :id, :user_id, :exchange, :enc_key, :enc_secret,
                true, :now, :now
            )
        """), {
            "id": api_key_id,
            "user_id": USER_ID,
            "exchange": "binance",
            "enc_key": encrypted_key,
            "enc_secret": encrypted_secret,
            "now": datetime.now(timezone.utc)
        })
        conn.commit()
        print(f"✅ Klucz dodany (ID: {api_key_id})")
    
    # Verify
    print("\n🔍 Weryfikacja...")
    result = conn.execute(text("""
        SELECT id, exchange, is_active, created_at, updated_at
        FROM public.api_keys
        WHERE user_id = :user_id AND exchange = 'binance'
    """), {"user_id": USER_ID})
    
    key_info = result.fetchone()
    if key_info:
        print("✅ Klucz API zapisany w bazie:")
        print(f"   ID: {key_info[0]}")
        print(f"   Exchange: {key_info[1]}")
        print(f"   Active: {key_info[2]}")
        print(f"   Created: {key_info[3]}")
        print(f"   Updated: {key_info[4]}")

print("\n" + "="*70)
print("✅ OPERACJA ZAKOŃCZONA POMYŚLNIE!")
print("="*70)
print(f"\n💡 Następne kroki:")
print(f"   1. Użytkownik może zalogować się do webappa")
print(f"   2. Email: {USER_EMAIL}")
print(f"   3. Dashboard pokaże połączony klucz Binance")
print(f"   4. Możesz uruchomić sync: python sync_binance_to_db.py")
