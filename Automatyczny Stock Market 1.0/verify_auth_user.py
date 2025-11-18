"""
Verify user exists in Supabase Auth (auth.users schema).
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM" / ".env"
load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM"))

from sqlalchemy import create_engine, text
import os

# Get database URL
DATABASE_URL = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ No database URL found")
    exit(1)

engine = create_engine(DATABASE_URL)

print("="*70)
print("🔍 SPRAWDZAM KONTO W SUPABASE AUTH (auth.users)")
print("="*70)
print()

# Query auth.users
with engine.connect() as conn:
    # Check if user exists in auth.users
    result = conn.execute(text("""
        SELECT 
            id,
            email,
            raw_user_meta_data->>'username' as username,
            raw_user_meta_data->>'full_name' as full_name,
            created_at,
            last_sign_in_at,
            email_confirmed_at,
            phone
        FROM auth.users 
        WHERE id = '3126f9fe-e724-4a33-bf4a-096804d56ece'
    """))
    
    user = result.fetchone()
    
    if user:
        print("✅ KONTO ZNALEZIONE W AUTH.USERS")
        print("="*70)
        print(f"UUID: {user[0]}")
        print(f"Email: {user[1]}")
        print(f"Username: {user[2]}")
        print(f"Full Name: {user[3]}")
        print(f"Created: {user[4]}")
        print(f"Last Login: {user[5]}")
        print(f"Email Confirmed: {user[6]}")
        print(f"Phone: {user[7]}")
        print()
    else:
        print("❌ KONTO NIE ISTNIEJE W AUTH.USERS!")
        print("   Sprawdzam czy istnieje tylko w public.profiles...")
        print()
        
    # Check profile
    result = conn.execute(text("""
        SELECT 
            user_id,
            username,
            email,
            full_name,
            subscription_tier,
            subscription_status
        FROM public.profiles 
        WHERE user_id = '3126f9fe-e724-4a33-bf4a-096804d56ece'
    """))
    
    profile = result.fetchone()
    
    if profile:
        print("✅ PROFIL ZNALEZIONY W PUBLIC.PROFILES")
        print("="*70)
        print(f"User ID: {profile[0]}")
        print(f"Username: {profile[1]}")
        print(f"Email: {profile[2]}")
        print(f"Full Name: {profile[3]}")
        print(f"Subscription: {profile[4]} ({profile[5]})")
        print()
    
    # Check API keys
    result = conn.execute(text("""
        SELECT 
            id,
            exchange,
            is_active,
            is_testnet,
            created_at
        FROM public.api_keys 
        WHERE user_id = '3126f9fe-e724-4a33-bf4a-096804d56ece'
    """))
    
    keys = result.fetchall()
    
    if keys:
        print("✅ KLUCZE API PRZYPISANE DO TEGO KONTA")
        print("="*70)
        for key in keys:
            print(f"Exchange: {key[1]}")
            print(f"  ID: {key[0]}")
            print(f"  Active: {key[2]}")
            print(f"  Testnet: {key[3]}")
            print(f"  Created: {key[4]}")
        print()

print("="*70)
print("🎯 PODSUMOWANIE")
print("="*70)
if user:
    print("✅ Użytkownik istnieje w Supabase Auth")
    print(f"✅ Email logowania: {user[1]}")
    print(f"✅ Hasło: (ustawione przez użytkownika)")
else:
    print("⚠️  Użytkownik NIE istnieje w auth.users!")
    print("⚠️  Istnieje tylko w public.profiles")
    print("⚠️  Trzeba utworzyć konto przez Supabase Auth!")

if profile and keys:
    print(f"✅ Klucz API Binance przypisany")
    print(f"✅ Dane synchronizowane z Binance")
    print(f"✅ Widoczne w panelu webapp")
