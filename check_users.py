#!/usr/bin/env python3
"""Check user accounts and API keys."""

import os
import sys
sys.path.insert(0, '.')

# Load from .env
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text

engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    # 1. Check user 4177e228 account details
    print('=' * 60)
    print('USER 4177e228 - ACCOUNT ANALYSIS')
    print('=' * 60)
    
    result = conn.execute(text("""
        SELECT u.id, u.email,
               ts.risk_level, ts.max_position_size, ts.max_daily_loss,
               ts.stop_loss_percentage, ts.take_profit_percentage
        FROM auth.users u
        LEFT JOIN trading_settings ts ON u.id = ts.user_id
        WHERE u.id::text LIKE '4177e228%'
    """)).fetchone()
    
    if result:
        print(f'User ID: {result[0]}')
        print(f'Email: {result[1]}')
        print(f'Risk Level: {result[2]}')
        print(f'Max Position Size: ${result[3]}')
        print(f'Max Daily Loss: ${result[4]}')
        print(f'SL: {result[5]}%, TP: {result[6]}%')
    
    # Check positions for user
    print()
    print('OPEN POSITIONS:')
    positions = conn.execute(text("""
        SELECT symbol, side, quantity, entry_price, stop_loss, take_profit, status
        FROM positions
        WHERE user_id::text LIKE '4177e228%' AND status = 'OPEN'
    """)).fetchall()
    
    for p in positions:
        value = float(p[2] or 0) * float(p[3] or 0)
        print(f'  {p[0]} {p[1]} | Qty: {p[2]} | Entry: ${p[3]} | Value: ${value:.2f}')
        print(f'    SL: ${p[4]} | TP: ${p[5]}')
    
    if not positions:
        print('  No open positions in DB')
    
    # Recent trades
    print()
    print('RECENT TRADES (last 5):')
    trades = conn.execute(text("""
        SELECT symbol, trade_type, amount, price, pnl, created_at
        FROM trades
        WHERE user_id::text LIKE '4177e228%'
        ORDER BY created_at DESC
        LIMIT 5
    """)).fetchall()
    
    for t in trades:
        pnl_str = f'${t[4]:.2f}' if t[4] else 'N/A'
        print(f'  {t[5]} | {t[1].upper()} {t[0]} | Amt: {t[2]} @ ${t[3]} | PnL: {pnl_str}')
    
    if not trades:
        print('  No trades found')
    
    print()
    print('=' * 60)
    print('USER e4f7f9e4 - API KEYS ANALYSIS')
    print('=' * 60)
    
    # Check ALL API keys for this user (encrypted columns)
    keys = conn.execute(text("""
        SELECT id, user_id, exchange, encrypted_api_key, encrypted_api_secret, 
               is_active, created_at, is_testnet, account_type
        FROM api_keys
        WHERE user_id::text LIKE 'e4f7f9e4%'
        ORDER BY created_at DESC
    """)).fetchall()
    
    print(f'Found {len(keys)} API key(s):')
    for k in keys:
        key_id = str(k[0])[:8] if k[0] else 'N/A'
        enc_key = str(k[3])[:30] if k[3] else 'N/A'
        enc_secret = str(k[4])[:20] if k[4] else 'N/A'
        print(f'  Key ID: {key_id}...')
        print(f'  Exchange: {k[2]}')
        print(f'  Encrypted Key: {enc_key}... (encrypted)')
        print(f'  Encrypted Secret: {enc_secret}... (encrypted)')
        print(f'  Active: {k[5]}')
        print(f'  Testnet: {k[7]}')
        print(f'  Account Type: {k[8]}')
        print(f'  Created: {k[6]}')
        print()
    
    if not keys:
        print('  NO API KEYS FOUND!')
        
        # Check if user exists
        user = conn.execute(text("""
            SELECT id, email FROM auth.users WHERE id::text LIKE 'e4f7f9e4%'
        """)).fetchone()
        
        if user:
            print(f'  User exists: {user[1]}')
            print('  But has no API keys configured!')
        else:
            print('  User does not exist in database!')
    
    # Also check ALL api_keys to see if there's a pattern
    print()
    print('=' * 60)
    print('ALL KRAKEN API KEYS IN DATABASE')
    print('=' * 60)
    
    all_keys = conn.execute(text("""
        SELECT ak.user_id, u.email, ak.exchange, ak.encrypted_api_key, ak.is_active, ak.account_type
        FROM api_keys ak
        LEFT JOIN auth.users u ON ak.user_id = u.id
        WHERE ak.exchange = 'kraken'
        ORDER BY ak.created_at DESC
    """)).fetchall()
    
    for k in all_keys:
        user_id = str(k[0])[:8] if k[0] else 'N/A'
        enc_key = str(k[3])[:20] if k[3] else 'N/A'
        print(f'  User: {user_id}... | Email: {k[1]} | Key: {enc_key}... | Active: {k[4]} | Type: {k[5]}')
