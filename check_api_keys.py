#!/usr/bin/env python3
"""Script to check API keys in database for specific users."""

import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

load_dotenv()

def check_api_keys():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return
    
    if "sslmode" not in db_url and "sqlite" not in db_url:
        db_url += "?sslmode=require"
        
    engine = create_engine(db_url)
    
    users = [
        '43e88b0b-d34f-4795-8efa-5507f40426e8',  # User 1
        'e4f7f9e4-5718-4857-b940-bb03f2bc4a1e'   # User 2
    ]
    
    with engine.connect() as conn:
        print("\n" + "="*60)
        print("SPRAWDZANIE KLUCZY API W BAZIE DANYCH")
        print("="*60)
        
        for user_id in users:
            print(f"\nUser: {user_id[:8]}...")
            
            # Check api_keys table - use encrypted columns!
            try:
                result = conn.execute(text("""
                    SELECT exchange, encrypted_api_key, encrypted_api_secret, is_active, created_at
                    FROM api_keys 
                    WHERE user_id = :user_id
                """), {"user_id": user_id}).fetchall()
                
                if result:
                    for row in result:
                        exchange = row[0]
                        enc_key = row[1]
                        enc_secret = row[2]
                        is_active = row[3]
                        created_at = row[4]
                        
                        active_str = "AKTYWNY" if is_active else "NIEAKTYWNY"
                        print(f"   Exchange: {exchange}")
                        print(f"   Encrypted Key len: {len(enc_key) if enc_key else 0}")
                        print(f"   Encrypted Secret len: {len(enc_secret) if enc_secret else 0}")
                        print(f"   Status: {active_str}")
                        print(f"   Created: {created_at}")
                else:
                    print("   BRAK KLUCZY API W TABELI api_keys!")
                    
            except Exception as e:
                print(f"   Blad: {e}")
        
        # Also show all Binance keys in DB
        print("\n" + "="*60)
        print("WSZYSTKIE KLUCZE BINANCE W BAZIE:")
        print("="*60)
        
        try:
            all_binance = conn.execute(text("""
                SELECT user_id, exchange, is_active, created_at
                FROM api_keys 
                WHERE exchange = 'binance'
                ORDER BY created_at DESC
            """)).fetchall()
            
            if all_binance:
                for row in all_binance:
                    status = "AKTYWNY" if row[2] else "NIEAKTYWNY"
                    print(f"   {status} | User: {row[0][:8]}... | Exchange: {row[1]} | Created: {row[3]}")
            else:
                print("   Brak kluczy Binance w bazie!")
                
        except Exception as e:
            print(f"   Blad: {e}")

if __name__ == "__main__":
    check_api_keys()
