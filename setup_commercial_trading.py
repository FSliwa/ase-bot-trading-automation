#!/usr/bin/env python3
"""
Commercial Trading Bot Setup Script
Konfiguracja i uruchomienie komercyjnego bota tradingowego dla konkretnego użytkownika
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client, Client

# Supabase connection
SUPABASE_URL = f"https://{os.getenv('SUPABASE_PROJECT_ID')}.supabase.co"
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_user_trading_config(email: str):
    """Pobierz konfigurację tradingową użytkownika"""
    
    print(f"\n🔍 Searching for user: {email}")
    
    # 1. Znajdź użytkownika
    user_result = supabase.table('profiles').select('*').eq('email', email).execute()
    
    if not user_result.data:
        print(f"❌ User {email} not found in database")
        return None
        
    user = user_result.data[0]
    user_id = user['user_id']
    
    print(f"✅ User found:")
    print(f"   ID: {user_id}")
    print(f"   Username: {user.get('username')}")
    print(f"   Full name: {user.get('full_name')}")
    print(f"   Subscription: {user.get('subscription_tier')}")
    
    # 2. Pobierz klucze API
    keys_result = supabase.table('api_keys').select('*').eq('user_id', user_id).eq('is_active', True).execute()
    
    if not keys_result.data:
        print(f"❌ No active API keys found for user")
        return None
        
    api_keys = keys_result.data
    print(f"\n🔑 API Keys ({len(api_keys)} active):")
    for key in api_keys:
        print(f"   - {key['exchange'].upper()} {'(TESTNET)' if key['is_testnet'] else '(LIVE)'}")
        print(f"     Key ID: {key['id']}")
        print(f"     Created: {key['created_at']}")
    
    # 3. Pobierz trading settings
    settings_result = supabase.table('trading_settings').select('*').eq('user_id', user_id).execute()
    
    trading_settings = []
    if settings_result.data:
        trading_settings = settings_result.data
        print(f"\n⚙️  Trading Settings ({len(trading_settings)} configurations):")
        for setting in trading_settings:
            print(f"   - Exchange: {setting.get('exchange').upper()}")
            print(f"     Trading enabled: {setting.get('is_trading_enabled')}")
            print(f"     Max position size: ${setting.get('max_position_size')}")
            print(f"     Max daily loss: ${setting.get('max_daily_loss')}")
            print(f"     Risk level: {setting.get('risk_level')}/5")
            print(f"     Preferred pairs: {setting.get('preferred_pairs')}")
    else:
        print(f"\n⚠️  No trading settings found - will use defaults")
    
    # 4. Sprawdź portfolio
    portfolio_result = supabase.table('portfolios').select('*').eq('user_id', user_id).execute()
    
    if portfolio_result.data:
        print(f"\n💼 Portfolio ({len(portfolio_result.data)} positions):")
        for pos in portfolio_result.data:
            balance = float(pos.get('balance', 0))
            if balance > 0:
                print(f"   - {pos['symbol']}: {balance} (${float(pos.get('avg_buy_price', 0)) * balance:.2f})")
    
    return {
        'user': user,
        'api_keys': api_keys,
        'trading_settings': trading_settings,
        'portfolio': portfolio_result.data if portfolio_result.data else []
    }


def enable_trading_for_user(email: str, exchange: str = 'binance'):
    """Włącz trading dla użytkownika"""
    
    user_result = supabase.table('profiles').select('user_id').eq('email', email).execute()
    if not user_result.data:
        print(f"❌ User {email} not found")
        return False
        
    user_id = user_result.data[0]['user_id']
    
    # Update trading settings
    update_result = supabase.table('trading_settings') \
        .update({'is_trading_enabled': True}) \
        .eq('user_id', user_id) \
        .eq('exchange', exchange) \
        .execute()
    
    if update_result.data:
        print(f"✅ Trading enabled for {email} on {exchange}")
        return True
    else:
        # Create new trading settings if not exists
        insert_result = supabase.table('trading_settings').insert({
            'user_id': user_id,
            'exchange': exchange,
            'is_trading_enabled': True,
            'max_position_size': 1000,
            'max_daily_loss': 100,
            'risk_level': 2,
            'preferred_pairs': ['BTC/USDT', 'ETH/USDT']
        }).execute()
        
        if insert_result.data:
            print(f"✅ Trading settings created and enabled for {email}")
            return True
        else:
            print(f"❌ Failed to enable trading")
            return False


def create_trading_bot_service(user_email: str):
    """Utwórz plik serwisu systemd dla bota tradingowego"""
    
    config = get_user_trading_config(user_email)
    if not config:
        return None
    
    user_id = config['user']['user_id']
    api_key = config['api_keys'][0] if config['api_keys'] else None
    
    if not api_key:
        print("❌ No API key available")
        return None
    
    exchange = api_key['exchange']
    is_testnet = api_key['is_testnet']
    
    service_content = f"""[Unit]
Description=ASE Trading Bot - User {user_email} ({exchange})
After=network.target

[Service]
Type=simple
User=admin
WorkingDirectory=/home/admin/asebot-backend/Algorytm Uczenia Kwantowego LLM
Environment="USER_ID={user_id}"
Environment="USER_EMAIL={user_email}"
Environment="EXCHANGE_NAME={exchange}"
Environment="USE_TESTNET={'true' if is_testnet else 'false'}"
ExecStart=/home/admin/asebot-backend/Algorytm Uczenia Kwantowego LLM/.venv/bin/python3 \\
  /home/admin/asebot-backend/Algorytm Uczenia Kwantowego LLM/commercial_trading_bot.py

Restart=always
RestartSec=10

StandardOutput=append:/var/log/asebot-trading-{user_id[:8]}.log
StandardError=append:/var/log/asebot-trading-{user_id[:8]}.err

[Install]
WantedBy=multi-user.target
"""
    
    service_file = f"asebot-trading-{user_id[:8]}.service"
    
    print(f"\n📝 Service file content ({service_file}):")
    print("=" * 80)
    print(service_content)
    print("=" * 80)
    
    return service_content, service_file


if __name__ == "__main__":
    print("=" * 80)
    print("🤖 ASE COMMERCIAL TRADING BOT - SETUP")
    print("=" * 80)
    
    # User to configure
    USER_EMAIL = "olofilip16@gmail.com"
    EXCHANGE = "binance"
    
    # Get configuration
    print("\n📊 Step 1: Fetching user configuration...")
    config = get_user_trading_config(USER_EMAIL)
    
    if not config:
        print("\n❌ Setup failed - user or API keys not found")
        sys.exit(1)
    
    # Check if trading is enabled
    print("\n📊 Step 2: Checking trading status...")
    trading_enabled = False
    for setting in config['trading_settings']:
        if setting.get('exchange') == EXCHANGE and setting.get('is_trading_enabled'):
            trading_enabled = True
            break
    
    if not trading_enabled:
        print(f"⚠️  Trading is DISABLED for {EXCHANGE}")
        response = input(f"Enable trading for {USER_EMAIL} on {EXCHANGE}? (yes/no): ")
        if response.lower() == 'yes':
            enable_trading_for_user(USER_EMAIL, EXCHANGE)
        else:
            print("❌ Trading not enabled - exiting")
            sys.exit(1)
    else:
        print(f"✅ Trading is already ENABLED for {EXCHANGE}")
    
    # Create service file
    print("\n📊 Step 3: Creating systemd service...")
    service_content, service_file = create_trading_bot_service(USER_EMAIL)
    
    # Save service file
    with open(f"/tmp/{service_file}", "w") as f:
        f.write(service_content)
    
    print(f"\n✅ Service file created: /tmp/{service_file}")
    print("\n📋 Next steps:")
    print(f"   1. sudo cp /tmp/{service_file} /etc/systemd/system/")
    print(f"   2. sudo systemctl daemon-reload")
    print(f"   3. sudo systemctl enable {service_file}")
    print(f"   4. sudo systemctl start {service_file}")
    print(f"   5. sudo systemctl status {service_file}")
    print(f"\n📊 Monitor logs:")
    print(f"   sudo journalctl -u {service_file} -f")
    
    print("\n" + "=" * 80)
    print("✅ SETUP COMPLETE")
    print("=" * 80)
