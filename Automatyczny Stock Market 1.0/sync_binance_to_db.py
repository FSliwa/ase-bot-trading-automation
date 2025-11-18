"""
Sync Binance account data to database for webapp display.
This script fetches real-time balance, positions, and trades from Binance
and stores them in the database so they appear in the user's dashboard.
"""
import sys
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone
from decimal import Decimal

# Load .env from the correct location
script_dir = Path(__file__).parent.absolute()
env_path = script_dir / "Algorytm Uczenia Kwantowego LLM" / ".env"
print(f"Loading .env from: {env_path}")
load_dotenv(env_path)

# Verify ENCRYPTION_KEY is loaded
enc_key = os.getenv("ENCRYPTION_KEY")
if enc_key:
    print(f"✅ ENCRYPTION_KEY loaded: {enc_key[:20]}...")
else:
    print("❌ WARNING: ENCRYPTION_KEY not found in .env!")

sys.path.insert(0, str(script_dir / "Algorytm Uczenia Kwantowego LLM"))

from bot.db import SessionLocal, PortfolioSnapshot
from bot.models import APIKey, Portfolio, Trade, PortfolioPerformance
from bot.security import get_security_manager
import ccxt

USER_ID = "47b49177-17e8-4426-a3f3-cfdafbf7b786"  # sky72199csgo@gmail.com

def sync_binance_data():
    """Sync Binance account data to database."""
    db = SessionLocal()
    security = get_security_manager()
    
    try:
        # 1. Get API credentials
        api_key = db.query(APIKey).filter_by(
            user_id=USER_ID,
            exchange="binance",
            is_active=True
        ).first()
        
        if not api_key:
            print("❌ No API key found")
            return
        
        # Decrypt
        api_key_str = security.decrypt(api_key.encrypted_api_key)
        api_secret_str = security.decrypt(api_key.encrypted_api_secret)
        
        # 2. Connect to Binance
        print("🔧 Connecting to Binance...")
        exchange = ccxt.binance({
            'apiKey': api_key_str,
            'secret': api_secret_str,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        
        # 3. Fetch account balance
        print("📊 Fetching balance...")
        balance = exchange.fetch_balance()
        total_balance_usd = 0.0
        
        # 4. Sync portfolio positions
        print("\n💼 Syncing portfolio positions...")
        for currency, amounts in balance['total'].items():
            if amounts > 0:
                # Get USD value
                try:
                    if currency == 'USDT':
                        usd_value = amounts
                        price = 1.0
                    else:
                        ticker = exchange.fetch_ticker(f"{currency}/USDT")
                        usd_value = amounts * ticker['last']
                        price = ticker['last']
                    
                    total_balance_usd += usd_value
                    
                    # Check if portfolio entry exists
                    portfolio = db.query(Portfolio).filter_by(
                        user_id=USER_ID,
                        exchange="binance",
                        symbol=currency
                    ).first()
                    
                    if portfolio:
                        # Update existing
                        portfolio.balance = Decimal(str(amounts))
                        portfolio.avg_buy_price = Decimal(str(price))
                        portfolio.total_invested = Decimal(str(usd_value))
                        portfolio.updated_at = datetime.now(timezone.utc)
                        print(f"   ✅ Updated {currency}: {amounts:.8f} (${usd_value:.2f})")
                    else:
                        # Create new
                        portfolio = Portfolio(
                            id=uuid.uuid4(),
                            user_id=USER_ID,
                            exchange="binance",
                            symbol=currency,
                            balance=Decimal(str(amounts)),
                            locked_balance=Decimal('0'),
                            avg_buy_price=Decimal(str(price)),
                            total_invested=Decimal(str(usd_value)),
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )
                        db.add(portfolio)
                        print(f"   ✅ Added {currency}: {amounts:.8f} (${usd_value:.2f})")
                        
                except Exception as e:
                    print(f"   ⚠️  Skipped {currency}: {e}")
        
        # 5. Create portfolio snapshot (for webapp API)
        print(f"\n📸 Creating portfolio snapshot for webapp...")
        snapshot = PortfolioSnapshot(
            user_id=USER_ID,
            total_balance=total_balance_usd,
            available_balance=balance['total'].get('USDT', 0),
            margin_used=0.0,
            unrealized_pnl=0.0,
            timestamp=datetime.now(timezone.utc),
            metadata_payload={
                'positions_value': total_balance_usd - balance['total'].get('USDT', 0),
                'exchange': 'binance'
            }
        )
        db.add(snapshot)
        print(f"   ✅ Total portfolio value: ${total_balance_usd:.2f}")
        print(f"   ✅ Available USDT: ${balance['total'].get('USDT', 0):.2f}")
        
        # 6. Fetch recent trades (last 100)
        print("\n📈 Syncing recent trades...")
        try:
            trades = exchange.fetch_my_trades(symbol='BTC/USDT', limit=100)
            for trade_data in trades[:10]:  # Store last 10 for demo
                # Check if trade exists
                existing = db.query(Trade).filter_by(
                    user_id=USER_ID,
                    exchange="binance",
                    symbol=trade_data['symbol']
                ).filter(
                    Trade.executed_at == datetime.fromtimestamp(trade_data['timestamp'] / 1000, tz=timezone.utc)
                ).first()
                
                if not existing:
                    trade = Trade(
                        id=uuid.uuid4(),
                        user_id=USER_ID,
                        exchange="binance",
                        symbol=trade_data['symbol'],
                        trade_type=trade_data['side'],  # buy/sell
                        amount=Decimal(str(trade_data['amount'])),
                        price=Decimal(str(trade_data['price'])),
                        fee=Decimal(str(trade_data['fee']['cost'])),
                        fee_currency=trade_data['fee']['currency'],
                        status='filled',
                        exchange_order_id=str(trade_data.get('order', '')),
                        created_at=datetime.fromtimestamp(trade_data['timestamp'] / 1000, tz=timezone.utc)
                    )
                    db.add(trade)
                    print(f"   ✅ {trade_data['side'].upper()} {trade_data['amount']} {trade_data['symbol']} @ ${trade_data['price']}")
        except Exception as e:
            print(f"   ⚠️  Could not fetch trades: {e}")
        
        # 7. Commit all changes
        db.commit()
        
        print("\n" + "="*60)
        print("✅ SYNCHRONIZATION COMPLETE!")
        print("="*60)
        print(f"\n📊 Summary:")
        print(f"   Total Portfolio Value: ${total_balance_usd:.2f}")
        print(f"   Cash (USDT): ${balance['total'].get('USDT', 0):.2f}")
        print(f"   Positions Value: ${total_balance_usd - balance['total'].get('USDT', 0):.2f}")
        print(f"\n💡 Data is now visible in webapp dashboard!")
        print(f"   Login as: filipsliwa")
        print(f"   Check: Portfolio, Positions, Recent Trades")
        
    except Exception as e:
        print(f"\n❌ Sync failed: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    sync_binance_data()
