"""
Migrate Binance API keys and data from olofilip16@gmail.com to f.sliwa@nowybankpolski.pl
"""
import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone

env_path = Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM" / ".env"
load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).parent / "Algorytm Uczenia Kwantowego LLM"))

from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

# Source and target user IDs
SOURCE_USER_ID = "3126f9fe-e724-4a33-bf4a-096804d56ece"  # olofilip16@gmail.com
TARGET_USER_ID = "2dc2d6d0-1aba-4689-8217-0206d7ebee62"  # f.sliwa@nowybankpolski.pl

print("="*70)
print("🔄 MIGRACJA DANYCH MIĘDZY KONTAMI")
print("="*70)
print(f"Źródło: olofilip16@gmail.com")
print(f"   UUID: {SOURCE_USER_ID}")
print(f"Cel: f.sliwa@nowybankpolski.pl")
print(f"   UUID: {TARGET_USER_ID}")
print("="*70)
print()

with engine.connect() as conn:
    # Start transaction
    trans = conn.begin()
    
    try:
        # 1. Check target account
        result = conn.execute(text("""
            SELECT email, raw_user_meta_data->>'username' as username
            FROM auth.users 
            WHERE id = :user_id
        """), {"user_id": TARGET_USER_ID})
        
        target_user = result.fetchone()
        
        if not target_user:
            print("❌ Docelowe konto nie istnieje!")
            exit(1)
            
        print(f"✅ Docelowe konto: {target_user[0]} (username: {target_user[1]})")
        print()
        
        # 2. Create or update profile for target user
        result = conn.execute(text("""
            SELECT user_id FROM public.profiles WHERE user_id = :user_id
        """), {"user_id": TARGET_USER_ID})
        
        if result.fetchone():
            print("✅ Profil już istnieje")
        else:
            print("📝 Tworzę profil dla docelowego użytkownika...")
            conn.execute(text("""
                INSERT INTO public.profiles (
                    user_id, username, email, full_name, 
                    subscription_tier, subscription_status
                )
                VALUES (
                    :user_id, :username, :email, 'Filip Sliwa',
                    'free', 'inactive'
                )
            """), {
                "user_id": TARGET_USER_ID,
                "username": target_user[1] or "fsliwa",
                "email": target_user[0]
            })
            print("✅ Profil utworzony")
        
        print()
        
        # 3. Migrate API Keys
        print("🔑 Migruję klucze API...")
        result = conn.execute(text("""
            UPDATE public.api_keys
            SET user_id = :target_user_id,
                updated_at = :now
            WHERE user_id = :source_user_id
            RETURNING id, exchange
        """), {
            "source_user_id": SOURCE_USER_ID,
            "target_user_id": TARGET_USER_ID,
            "now": datetime.now(timezone.utc)
        })
        
        migrated_keys = result.fetchall()
        for key_id, exchange in migrated_keys:
            print(f"   ✅ {exchange} API key (ID: {key_id})")
        
        # 4. Migrate Portfolio
        print("\n💼 Migruję portfolio...")
        result = conn.execute(text("""
            UPDATE public.portfolios
            SET user_id = :target_user_id,
                updated_at = :now
            WHERE user_id = :source_user_id
            RETURNING id, symbol, balance
        """), {
            "source_user_id": SOURCE_USER_ID,
            "target_user_id": TARGET_USER_ID,
            "now": datetime.now(timezone.utc)
        })
        
        migrated_portfolios = result.fetchall()
        for port_id, symbol, balance in migrated_portfolios:
            print(f"   ✅ {symbol}: {balance}")
        
        # 5. Migrate Trades
        print("\n📈 Migruję historię transakcji...")
        result = conn.execute(text("""
            UPDATE public.trades
            SET user_id = :target_user_id
            WHERE user_id = :source_user_id
            RETURNING id
        """), {
            "source_user_id": SOURCE_USER_ID,
            "target_user_id": TARGET_USER_ID
        })
        
        trade_count = len(result.fetchall())
        print(f"   ✅ {trade_count} transakcji")
        
        # 6. Migrate Trading Settings - delete old ones (target account already has its own)
        print("\n⚙️  Usuwam stare ustawienia tradingu ze źródłowego konta...")
        result = conn.execute(text("""
            DELETE FROM public.trading_settings
            WHERE user_id = :source_user_id
            RETURNING id, exchange
        """), {
            "source_user_id": SOURCE_USER_ID
        })
        
        settings = result.fetchall()
        for setting_id, exchange in settings:
            print(f"   ✅ Usunięto {exchange} settings")
        
        print("   ℹ️  Docelowe konto zachowuje swoje istniejące ustawienia")
        
        # 7. Migrate Portfolio Performance
        print("\n📊 Migruję portfolio performance...")
        result = conn.execute(text("""
            UPDATE public.portfolio_performance
            SET user_id = :target_user_id
            WHERE user_id = :source_user_id
            RETURNING id
        """), {
            "source_user_id": SOURCE_USER_ID,
            "target_user_id": TARGET_USER_ID
        })
        
        perf_count = len(result.fetchall())
        print(f"   ✅ {perf_count} rekordów")
        
        # 8. Migrate Portfolio Snapshots (from bot.db)
        print("\n📸 Migruję portfolio snapshots...")
        result = conn.execute(text("""
            UPDATE public.portfolio_snapshots
            SET user_id = :target_user_id
            WHERE user_id = :source_user_id
            RETURNING id
        """), {
            "source_user_id": SOURCE_USER_ID,
            "target_user_id": TARGET_USER_ID
        })
        
        snapshot_count = len(result.fetchall())
        print(f"   ✅ {snapshot_count} snapshots")
        
        # Commit transaction
        trans.commit()
        
        print()
        print("="*70)
        print("✅ MIGRACJA ZAKOŃCZONA POMYŚLNIE!")
        print("="*70)
        print()
        print("📋 Podsumowanie:")
        print(f"   - Klucze API: {len(migrated_keys)}")
        print(f"   - Portfolio pozycje: {len(migrated_portfolios)}")
        print(f"   - Transakcje: {trade_count}")
        print(f"   - Ustawienia: {len(settings)}")
        print(f"   - Performance: {perf_count}")
        print(f"   - Snapshots: {snapshot_count}")
        print()
        print("🎯 Nowe dane logowania:")
        print(f"   Email: {target_user[0]}")
        print(f"   Username: {target_user[1] or 'fsliwa'}")
        print(f"   Hasło: (niezmienione)")
        print()
        print("✅ Wszystkie dane Binance są teraz widoczne w panelu tego konta!")
        
    except Exception as e:
        trans.rollback()
        print(f"\n❌ BŁĄD MIGRACJI: {e}")
        import traceback
        traceback.print_exc()
        raise
