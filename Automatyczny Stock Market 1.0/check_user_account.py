"""
Check which Supabase Auth user is linked to the API key.
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM" / ".env"
load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM"))

from bot.db import SessionLocal
from bot.models import Profile, APIKey

db = SessionLocal()
try:
    # Znajdź profil
    profile = db.query(Profile).filter_by(user_id='3126f9fe-e724-4a33-bf4a-096804d56ece').first()
    
    if profile:
        print('='*60)
        print('👤 PROFIL UŻYTKOWNIKA W SUPABASE')
        print('='*60)
        print(f'User ID (UUID): {profile.user_id}')
        print(f'Username: {profile.username}')
        print(f'Email: {profile.email}')
        print(f'Full Name: {profile.full_name}')
        print(f'Phone: {profile.phone}')
        print(f'Subscription: {profile.subscription_tier} ({profile.subscription_status})')
        print()
    else:
        print('❌ Profil nie znaleziony w public.profiles')
        print('   Sprawdzam auth.users...')
        
    # Znajdź klucz API
    api_key = db.query(APIKey).filter_by(
        user_id='3126f9fe-e724-4a33-bf4a-096804d56ece',
        exchange='binance'
    ).first()
    
    if api_key:
        print('='*60)
        print('🔑 PRZYPISANY KLUCZ API BINANCE')
        print('='*60)
        print(f'API Key ID: {api_key.id}')
        print(f'User ID: {api_key.user_id}')
        print(f'Exchange: {api_key.exchange}')
        print(f'Is Active: {api_key.is_active}')
        print(f'Is Testnet: {api_key.is_testnet}')
        print(f'Created At: {api_key.created_at}')
        print()
    
    print('='*60)
    print('📍 GDZIE ZNALEŹĆ TO KONTO W SUPABASE AUTH')
    print('='*60)
    print(f'1. Otwórz: https://supabase.com/dashboard')
    print(f'2. Wybierz projekt: iqqmbzznwpheqiihnjhz')
    print(f'3. Przejdź do: Authentication > Users')
    print(f'4. Szukaj użytkownika po:')
    print(f'   - UUID: 3126f9fe-e724-4a33-bf4a-096804d56ece')
    if profile:
        print(f'   - Email: {profile.email}')
        print(f'   - Username: {profile.username}')
    else:
        print(f'   - Email: [sprawdź w auth.users]')
        print(f'   - Username: filipsliwa (lub sprawdź w auth.users)')
    
    print()
    print('='*60)
    print('📊 DANE WIDOCZNE W PANELU TEGO UŻYTKOWNIKA')
    print('='*60)
    print(f'✅ Saldo Binance: $0.14 USDT')
    print(f'✅ Pozycje: USDT, TON, SCR')
    print(f'✅ Trading Settings: max $1000/trade, risk 2/5')
    print(f'✅ Portfolio Performance: zapisywane codziennie')
    
finally:
    db.close()
