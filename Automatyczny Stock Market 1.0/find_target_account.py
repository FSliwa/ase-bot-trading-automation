"""
Find and verify f.sliwa@nowybanpolski.pl account in Supabase.
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM" / ".env"
load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM"))

from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

print("="*70)
print("🔍 SZUKAM KONTA: f.sliwa@nowybanpolski.pl")
print("="*70)
print()

with engine.connect() as conn:
    # Search in auth.users
    result = conn.execute(text("""
        SELECT 
            id,
            email,
            raw_user_meta_data->>'username' as username,
            raw_user_meta_data->>'full_name' as full_name,
            created_at,
            last_sign_in_at,
            email_confirmed_at
        FROM auth.users 
        WHERE email = 'f.sliwa@nowybanpolski.pl'
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
        print()
        
        TARGET_USER_ID = str(user[0])
        
        # Check if profile exists
        result = conn.execute(text("""
            SELECT user_id, username, email, full_name
            FROM public.profiles 
            WHERE user_id = :user_id
        """), {"user_id": TARGET_USER_ID})
        
        profile = result.fetchone()
        
        if profile:
            print("✅ PROFIL ISTNIEJE W PUBLIC.PROFILES")
            print(f"   Username: {profile[1]}")
            print(f"   Email: {profile[2]}")
            print()
        else:
            print("⚠️  PROFIL NIE ISTNIEJE W PUBLIC.PROFILES")
            print("   Zostanie utworzony podczas migracji")
            print()
        
        # Check existing API keys
        result = conn.execute(text("""
            SELECT id, exchange, is_active
            FROM public.api_keys 
            WHERE user_id = :user_id
        """), {"user_id": TARGET_USER_ID})
        
        existing_keys = result.fetchall()
        
        if existing_keys:
            print("⚠️  TO KONTO MA JUŻ KLUCZE API:")
            for key in existing_keys:
                print(f"   - {key[1]} (Active: {key[2]}, ID: {key[0]})")
            print()
        else:
            print("✅ KONTO NIE MA JESZCZE KLUCZY API - gotowe do migracji")
            print()
            
        print("="*70)
        print("🎯 PLAN MIGRACJI")
        print("="*70)
        print(f"✅ Docelowe konto znalezione: {user[1]}")
        print(f"✅ UUID docelowy: {TARGET_USER_ID}")
        print()
        print("Operacje do wykonania:")
        print("1. Przenieś klucz API Binance")
        print("2. Przenieś portfolio positions")
        print("3. Przenieś portfolio snapshots")
        print("4. Przenieś trading settings")
        print("5. Przenieś trades history")
        print("6. Przenieś portfolio performance")
        
    else:
        print("❌ KONTO NIE ZNALEZIONE W AUTH.USERS!")
        print()
        print("Szukam podobnych kont...")
        
        # Search similar emails
        result = conn.execute(text("""
            SELECT email, id
            FROM auth.users 
            WHERE email ILIKE '%sliwa%' OR email ILIKE '%nowybanpolski%'
        """))
        
        similar = result.fetchall()
        
        if similar:
            print("\n📧 Znalezione podobne konta:")
            for email, uid in similar:
                print(f"   - {email} (UUID: {uid})")
        else:
            print("\n❌ Nie znaleziono żadnych podobnych kont")
            
        print()
        print("="*70)
        print("⚠️  AKCJA WYMAGANA")
        print("="*70)
        print("Konto f.sliwa@nowybanpolski.pl nie istnieje w Supabase Auth.")
        print()
        print("Opcje:")
        print("1. Utwórz konto przez Supabase Dashboard:")
        print("   - Authentication > Add User")
        print("   - Email: f.sliwa@nowybanpolski.pl")
        print("   - Password: (ustaw własne)")
        print()
        print("2. Zarejestruj się przez webapp")
        print()
        print("3. Podaj inne istniejące konto email")
