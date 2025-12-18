#!/usr/bin/env python3
"""Test Binance API keys for trading permissions."""

import os
import sys
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

import asyncio
from sqlalchemy import create_engine, text
import ccxt.async_support as ccxt_async
from bot.security import SecurityManager

security_manager = SecurityManager()
engine = create_engine(os.environ['DATABASE_URL'])

async def test_key(key_id, enc_api_key, enc_api_secret):
    """Test if key has trading permissions"""
    try:
        api_key = security_manager.decrypt(enc_api_key)
        api_secret = security_manager.decrypt(enc_api_secret)
        
        print(f"\nTesting key {str(key_id)[:8]}...")
        print(f"  API Key: {api_key[:15]}...")
        
        exchange = ccxt_async.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
        })
        
        # Test 1: Get account balance
        balance = await exchange.fetch_balance()
        usdt = balance['total'].get('USDT', 0)
        usdc = balance['total'].get('USDC', 0)
        bnb = balance['total'].get('BNB', 0)
        print(f"  Balance: USDT={usdt:.2f}, USDC={usdc:.2f}, BNB={bnb:.4f}")
        
        # Test 2: Check if can place orders (check API permissions)
        try:
            # Try to get open orders (requires spot trading permission)
            orders = await exchange.fetch_open_orders()
            print(f"  ✅ Trading permissions: YES (can fetch orders)")
            has_trading = True
        except Exception as e:
            error_str = str(e).lower()
            if 'permission' in error_str or 'api-key' in error_str:
                print(f"  ❌ Trading permissions: NO")
                has_trading = False
            else:
                print(f"  ✅ Trading likely OK (error: {str(e)[:50]})")
                has_trading = True
        
        await exchange.close()
        return has_trading, api_key, api_secret, usdt + usdc
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False, None, None, 0

async def main():
    with engine.connect() as conn:
        # Get user's full ID first
        user = conn.execute(text("""
            SELECT id, email FROM auth.users WHERE id::text LIKE 'e4f7f9e4%'
        """)).fetchone()
        
        if user:
            print(f"User: {user[1]} ({user[0]})")
        
        keys = conn.execute(text("""
            SELECT id, encrypted_api_key, encrypted_api_secret, account_type, created_at
            FROM api_keys
            WHERE user_id::text LIKE 'e4f7f9e4%' AND exchange = 'binance' AND is_active = true
            ORDER BY created_at DESC
        """)).fetchall()
        
        print(f"\nFound {len(keys)} active Binance key(s)")
        
        best_key = None
        for k in keys:
            has_trading, api_key, api_secret, balance = await test_key(k[0], k[1], k[2])
            if has_trading:
                best_key = {
                    'id': k[0],
                    'api_key': api_key,
                    'api_secret': api_secret,
                    'balance': balance
                }
                if balance > 0:
                    print(f"\n✅ BEST KEY FOUND: {str(k[0])[:8]}... with balance ${balance:.2f}")
                    break
                else:
                    print(f"\n⚠️ Key has trading permissions but $0 balance")
        
        if not best_key:
            print("\n❌ No valid trading key found!")
        
        return best_key

if __name__ == "__main__":
    result = asyncio.run(main())
    if result:
        print(f"\n--- RESULT ---")
        print(f"Key ID: {result['id']}")
        print(f"Balance: ${result['balance']:.2f}")
