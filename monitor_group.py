
import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import datetime
from datetime import timedelta

# Load .env at the very start
load_dotenv()

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# ============================================================
# SUPABASE DIRECT CLIENT (for realtime data)
# ============================================================
try:
    from supabase import create_client, Client
    SUPABASE_CLIENT_AVAILABLE = True
except ImportError:
    SUPABASE_CLIENT_AVAILABLE = False
    print("⚠️ supabase-py not installed. Install with: pip install supabase")

# SQLAlchemy for DB access
try:
    from sqlalchemy import create_engine, text
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False

from bot.security import get_security_manager
from bot.exchange_adapters.ccxt_adapter import CCXTAdapter, Position

# Removed hardcoded USERS list - now fetched dynamically from database


# ============================================================
# SUPABASE API CLIENT (for realtime Supabase data)
# ============================================================
def get_supabase_client() -> 'Client':
    """Create Supabase client from environment."""
    if not SUPABASE_CLIENT_AVAILABLE:
        return None
    
    # Try different env var names
    supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("⚠️ Supabase credentials not found in environment")
        return None
    
    try:
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        print(f"⚠️ Failed to create Supabase client: {e}")
        return None


async def get_monthly_pnl_from_supabase(supabase: 'Client', user_id: str) -> dict:
    """
    Fetch monthly P&L statistics directly from Supabase API.
    ENHANCED: Better handling of closed trades and realized P&L.
    """
    result = {
        'total_pnl': 0.0,
        'realized_pnl': 0.0,
        'trade_count': 0,
        'winning_trades': 0,
        'losing_trades': 0,
        'win_rate': 0.0,
        'avg_win': 0.0,
        'avg_loss': 0.0,
        'best_trade': 0.0,
        'worst_trade': 0.0,
        'total_volume': 0.0,
        'recent_trades': [],
        'all_time_trades': 0,  # Total trades ever
        'all_time_pnl': 0.0    # All-time P&L
    }
    
    if not supabase:
        return result
    
    try:
        thirty_days_ago = (datetime.datetime.now() - timedelta(days=30)).isoformat()
        all_trades = []
        
        # === PRIMARY SOURCE: trades table (has user_id, pnl, entry/exit prices) ===
        try:
            # FIX 2025-12-17: trades table is the PRIMARY source for closed trades
            # It has: user_id, pnl, entry_price, exit_price, amount, trade_type
            response = supabase.table("trades").select(
                "symbol, trade_type, amount, price, entry_price, exit_price, pnl, status, emotion, executed_at, created_at, updated_at"
            ).eq("user_id", user_id).eq("status", "completed").order("created_at", desc=True).limit(200).execute()
            
            if response.data:
                print(f"      📊 Found {len(response.data)} completed trades in DB")
                for row in response.data:
                    # PnL is stored directly in trades table
                    pnl = float(row.get('pnl') or 0)
                    entry = float(row.get('entry_price') or row.get('price') or 0)
                    exit_p = float(row.get('exit_price') or row.get('price') or 0)
                    qty = float(row.get('amount') or 0)
                    
                    # Calculate P&L if not stored but we have entry/exit
                    if pnl == 0 and entry > 0 and exit_p > 0 and qty > 0:
                        side = str(row.get('trade_type') or 'buy').lower()
                        if side in ('buy', 'long'):
                            pnl = (exit_p - entry) * qty
                        else:
                            pnl = (entry - exit_p) * qty
                    
                    all_trades.append({
                        'symbol': row.get('symbol'),
                        'side': row.get('trade_type'),
                        'quantity': qty,
                        'entry_price': entry,
                        'exit_price': exit_p,
                        'pnl': pnl,
                        'close_reason': row.get('emotion') or row.get('status'),
                        'closed_at': row.get('created_at') or row.get('executed_at') or row.get('updated_at'),
                        'created_at': row.get('created_at'),
                        'source': 'trades'
                    })
        except Exception as e:
            print(f"      ⚠️ trades table error: {e}")
        
        # === SECONDARY SOURCE: positions table (often has user_id=NULL, so less reliable) ===
        try:
            response = supabase.table("positions").select(
                "symbol, side, quantity, entry_price, current_price, realized_pnl, close_reason, exit_time, created_at"
            ).eq("user_id", user_id).eq("status", "CLOSED").order("exit_time", desc=True).limit(100).execute()
            
            if response.data:
                print(f"      📊 Found {len(response.data)} closed positions in DB")
                for row in response.data:
                    pnl = float(row.get('realized_pnl') or 0)
                    entry = float(row.get('entry_price') or 0)
                    exit_p = float(row.get('current_price') or 0)
                    qty = float(row.get('quantity') or 0)
                    
                    # Calculate P&L if not stored
                    if pnl == 0 and entry > 0 and exit_p > 0 and qty > 0:
                        side = str(row.get('side') or 'long').lower()
                        if side in ('buy', 'long'):
                            pnl = (exit_p - entry) * qty
                        else:
                            pnl = (entry - exit_p) * qty
                    
                    all_trades.append({
                        'symbol': row.get('symbol'),
                        'side': row.get('side'),
                        'quantity': qty,
                        'entry_price': entry,
                        'exit_price': exit_p,
                        'pnl': pnl,
                        'close_reason': row.get('close_reason'),
                        'closed_at': row.get('exit_time') or row.get('created_at'),
                        'created_at': row.get('created_at'),
                        'source': 'positions'
                    })
        except Exception as e:
            print(f"      ⚠️ positions table error: {e}")
        
        # === SOURCE 3: monitored_positions (closed) ===
        try:
            response = supabase.table("monitored_positions").select(
                "symbol, side, quantity, entry_price, stop_loss, take_profit, closed_at, is_active"
            ).eq("user_id", user_id).eq("is_active", False).order("closed_at", desc=True).limit(50).execute()
            
            # Note: monitored_positions doesn't have direct P&L, would need price lookup
        except Exception:
            pass  # Table may not exist
        
        # Process all trades
        if all_trades:
            pnl_values = []
            seen_trades = set()
            recent_count = 0
            
            # Sort by closed_at descending
            sorted_trades = sorted(
                all_trades,
                key=lambda t: t.get('closed_at') or '1970-01-01',
                reverse=True
            )
            
            for trade in sorted_trades:
                # Deduplicate
                trade_key = f"{trade['symbol']}_{trade['entry_price']}_{trade['closed_at']}"
                if trade_key in seen_trades:
                    continue
                seen_trades.add(trade_key)
                
                pnl = trade['pnl']
                
                # Calculate P&L if not present
                if pnl == 0 and trade['entry_price'] and trade['exit_price']:
                    entry = trade['entry_price']
                    exit_p = trade['exit_price']
                    qty = trade['quantity']
                    side = str(trade['side'] or 'buy').lower()
                    
                    if side in ('buy', 'long'):
                        pnl = (exit_p - entry) * qty
                    else:
                        pnl = (entry - exit_p) * qty
                
                # Check if within 30 days
                trade_date_str = trade.get('closed_at')
                if trade_date_str:
                    try:
                        if isinstance(trade_date_str, str):
                            # Handle ISO format with or without timezone
                            trade_date_str = trade_date_str.replace('Z', '+00:00')
                            if '+' not in trade_date_str and '-' not in trade_date_str[10:]:
                                trade_date = datetime.datetime.fromisoformat(trade_date_str)
                            else:
                                trade_date = datetime.datetime.fromisoformat(trade_date_str)
                        else:
                            trade_date = trade_date_str
                        
                        trade_date_naive = trade_date.replace(tzinfo=None) if hasattr(trade_date, 'tzinfo') and trade_date.tzinfo else trade_date
                        thirty_days_ago_dt = datetime.datetime.now() - timedelta(days=30)
                        
                        if trade_date_naive >= thirty_days_ago_dt:
                            pnl_values.append(pnl)
                            if pnl > 0:
                                result['winning_trades'] += 1
                            elif pnl < 0:
                                result['losing_trades'] += 1
                    except Exception as date_err:
                        # Still count the trade if date parsing fails
                        pnl_values.append(pnl)
                        if pnl > 0:
                            result['winning_trades'] += 1
                        elif pnl < 0:
                            result['losing_trades'] += 1
                
                # Store recent trades
                if recent_count < 10:
                    result['recent_trades'].append({
                        'symbol': trade['symbol'],
                        'side': str(trade['side'] or 'unknown'),
                        'pnl': pnl,
                        'entry': trade['entry_price'],
                        'exit': trade['exit_price'],
                        'quantity': trade['quantity'],
                        'reason': trade['close_reason'],
                        'closed_at': trade['closed_at'],
                        'source': trade['source']
                    })
                    recent_count += 1
            
            result['trade_count'] = len(pnl_values)
            result['total_pnl'] = sum(pnl_values)
            result['realized_pnl'] = sum(pnl_values)
            
            # All-time stats (all trades, not just 30 days)
            all_pnls = [t['pnl'] for t in sorted_trades if t['pnl'] != 0]
            result['all_time_trades'] = len(all_pnls)
            result['all_time_pnl'] = sum(all_pnls)
            
            if result['trade_count'] > 0:
                result['win_rate'] = (result['winning_trades'] / result['trade_count']) * 100
            
            winning_pnls = [p for p in pnl_values if p > 0]
            losing_pnls = [p for p in pnl_values if p < 0]
            
            if winning_pnls:
                result['avg_win'] = sum(winning_pnls) / len(winning_pnls)
                result['best_trade'] = max(winning_pnls)
            
            if losing_pnls:
                result['avg_loss'] = sum(losing_pnls) / len(losing_pnls)
                result['worst_trade'] = min(losing_pnls)
    
    except Exception as e:
        print(f"      ⚠️ Supabase P&L fetch error: {e}")
    
    return result


async def get_monthly_pnl_from_db(engine, user_id: str) -> dict:
    """Fetch monthly P&L statistics from trades and positions tables."""
    result = {
        'total_pnl': 0.0,
        'realized_pnl': 0.0,  # NEW: Explicit realized P&L
        'trade_count': 0,
        'winning_trades': 0,
        'losing_trades': 0,
        'win_rate': 0.0,
        'avg_win': 0.0,
        'avg_loss': 0.0,
        'best_trade': 0.0,
        'worst_trade': 0.0,
        'total_volume': 0.0,
        'recent_trades': []  # List of recent closed trades
    }
    
    try:
        with engine.connect() as conn:
            # Get trades from last 30 days
            thirty_days_ago = datetime.datetime.now() - timedelta(days=30)
            
            all_trades = []
            
            # === SOURCE 1: Try 'trades' table ===
            try:
                query = text("""
                    SELECT 
                        symbol,
                        COALESCE(side, trade_type) as side,
                        COALESCE(quantity, amount) as quantity,
                        COALESCE(entry_price, price) as entry_price,
                        exit_price,
                        pnl,
                        close_reason,
                        COALESCE(closed_at, updated_at) as closed_at,
                        created_at,
                        'trades' as source
                    FROM trades 
                    WHERE user_id = :user_id 
                    AND (exit_price IS NOT NULL OR pnl IS NOT NULL)
                    ORDER BY closed_at DESC NULLS LAST
                    LIMIT 50
                """)
                trades = conn.execute(query, {"user_id": user_id}).fetchall()
                all_trades.extend(trades)
            except Exception as e1:
                pass  # Table may not exist or have different schema
            
            # === SOURCE 2: Try 'positions' table (closed positions) ===
            try:
                query = text("""
                    SELECT 
                        symbol,
                        side,
                        quantity,
                        entry_price,
                        current_price as exit_price,
                        realized_pnl as pnl,
                        close_reason,
                        exit_time as closed_at,
                        created_at,
                        'positions' as source
                    FROM positions 
                    WHERE user_id = :user_id 
                    AND status = 'CLOSED'
                    ORDER BY exit_time DESC NULLS LAST
                    LIMIT 50
                """)
                positions = conn.execute(query, {"user_id": user_id}).fetchall()
                all_trades.extend(positions)
            except Exception as e2:
                pass  # Table may not exist
            
            # === SOURCE 3: Try 'fills' or 'orders' table ===
            try:
                query = text("""
                    SELECT 
                        symbol,
                        side,
                        COALESCE(filled_quantity, quantity) as quantity,
                        price as entry_price,
                        avg_fill_price as exit_price,
                        0 as pnl,
                        status as close_reason,
                        updated_at as closed_at,
                        created_at,
                        'orders' as source
                    FROM orders 
                    WHERE user_id = :user_id 
                    AND status = 'FILLED'
                    ORDER BY updated_at DESC
                    LIMIT 20
                """)
                orders = conn.execute(query, {"user_id": user_id}).fetchall()
                # Don't add orders - they don't have real P&L
            except Exception:
                pass
            
            if all_trades:
                pnl_values = []
                recent_count = 0
                seen_trades = set()  # Avoid duplicates
                
                # Sort by closed_at descending
                sorted_trades = sorted(
                    all_trades, 
                    key=lambda t: t.closed_at or datetime.datetime.min.replace(tzinfo=None),
                    reverse=True
                )
                
                for trade in sorted_trades:
                    # Create unique key to avoid duplicates
                    trade_key = f"{trade.symbol}_{trade.entry_price}_{trade.closed_at}"
                    if trade_key in seen_trades:
                        continue
                    seen_trades.add(trade_key)
                    
                    pnl = float(trade.pnl or 0)
                    
                    # If no P&L but we have entry and exit, calculate it
                    if pnl == 0 and trade.entry_price and trade.exit_price:
                        entry = float(trade.entry_price)
                        exit_p = float(trade.exit_price)
                        qty = float(trade.quantity or 0)
                        side = str(trade.side or 'buy').lower()
                        
                        if side in ('buy', 'long'):
                            pnl = (exit_p - entry) * qty
                        else:
                            pnl = (entry - exit_p) * qty
                    
                    # Check if within 30 days
                    trade_date = trade.closed_at
                    if trade_date:
                        if isinstance(trade_date, str):
                            try:
                                trade_date = datetime.datetime.fromisoformat(trade_date.replace('Z', '+00:00'))
                            except:
                                trade_date = None
                        
                        if trade_date:
                            trade_date_naive = trade_date.replace(tzinfo=None) if trade_date.tzinfo else trade_date
                            if trade_date_naive >= thirty_days_ago:
                                pnl_values.append(pnl)
                                
                                if pnl > 0:
                                    result['winning_trades'] += 1
                                elif pnl < 0:
                                    result['losing_trades'] += 1
                    
                    # Store recent trades (last 10)
                    if recent_count < 10:
                        close_reason = str(trade.close_reason or 'unknown')
                        result['recent_trades'].append({
                            'symbol': trade.symbol,
                            'side': str(trade.side or 'unknown'),
                            'pnl': pnl,
                            'entry': float(trade.entry_price or 0),
                            'exit': float(trade.exit_price or 0),
                            'quantity': float(trade.quantity or 0),
                            'reason': close_reason,
                            'closed_at': trade.closed_at,
                            'source': getattr(trade, 'source', 'unknown')
                        })
                        recent_count += 1
                
                result['trade_count'] = len(pnl_values)
                result['total_pnl'] = sum(pnl_values)
                result['realized_pnl'] = sum(pnl_values)  # Explicit realized
                
                if result['trade_count'] > 0:
                    result['win_rate'] = (result['winning_trades'] / result['trade_count']) * 100
                
                winning_pnls = [p for p in pnl_values if p > 0]
                losing_pnls = [p for p in pnl_values if p < 0]
                
                if winning_pnls:
                    result['avg_win'] = sum(winning_pnls) / len(winning_pnls)
                    result['best_trade'] = max(winning_pnls)
                
                if losing_pnls:
                    result['avg_loss'] = sum(losing_pnls) / len(losing_pnls)
                    result['worst_trade'] = min(losing_pnls)
                    
    except Exception as e:
        # Log error for debugging
        print(f"      ⚠️ P&L fetch error: {e}")
    
    return result

async def get_all_users_from_db(engine) -> list:
    """Fetch all users with API keys from database."""
    users = []
    try:
        with engine.connect() as conn:
            # Get all unique user_ids that have API keys configured
            query = text("""
                SELECT DISTINCT user_id, exchange, is_testnet 
                FROM api_keys 
                WHERE encrypted_api_key IS NOT NULL 
                ORDER BY user_id
            """)
            result = conn.execute(query).fetchall()
            
            for row in result:
                users.append({
                    'user_id': row.user_id,
                    'exchange': row.exchange,
                    'is_testnet': row.is_testnet
                })
                
        print(f"📋 Found {len(users)} users with API keys in database")
    except Exception as e:
        print(f"❌ Error fetching users: {e}")
    
    return users

async def monitor_group():
    load_dotenv()
    
    # Database setup - try multiple sources
    SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
    DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")
    
    # Fallback: try to read from local .env or trading.db
    if not DATABASE_URL:
        # Check if local trading.db exists
        local_db = Path(__file__).parent / "trading.db"
        if local_db.exists():
            DATABASE_URL = f"sqlite:///{local_db}"
            print(f"⚠️ Using local SQLite database: {local_db}")
        else:
            print("❌ No DATABASE_URL configured!")
            print("   Set SUPABASE_DB_URL environment variable:")
            print("   export SUPABASE_DB_URL='postgresql://user:pass@host:5432/postgres'")
            print("")
            print("   Or create a .env file with:")
            print("   SUPABASE_DB_URL=postgresql://user:pass@host:5432/postgres")
            return
    
    if DATABASE_URL and "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"
    
    if not DATABASE_URL:
        print("❌ No DATABASE_URL configured!")
        return
    
    engine = create_engine(DATABASE_URL)
    security_manager = get_security_manager()
    
    # === NEW: Create Supabase API client for realtime data ===
    supabase_client = get_supabase_client()
    if supabase_client:
        print(f"✅ Supabase API client connected")
    else:
        print(f"⚠️ Supabase API client not available - using SQLAlchemy only")
    
    print(f"🚀 Starting Continuous Group Monitor (Interval: 60s)...")
    print(f"📡 Database: {DATABASE_URL[:50]}...")
    
    while True:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'='*70}")
        print(f"📊 --- ALL USERS MONITOR --- {timestamp}")
        print(f"{'='*70}")
        
        # Fetch ALL users dynamically from database
        users = await get_all_users_from_db(engine)
        
        if not users:
            print("⚠️ No users found in database. Waiting...")
            await asyncio.sleep(60)
            continue
        
        total_equity_all = 0.0
        total_pnl_all = 0.0
        total_monthly_pnl_all = 0.0
        total_monthly_trades_all = 0
        active_users = 0
        
        for user_info in users:
            user_id = user_info['user_id']
            try:
                print(f"\n👤 User: {user_id}")
                
                # Fetch credentials
                with engine.connect() as conn:
                    query = text("SELECT encrypted_api_key, encrypted_api_secret, exchange, is_testnet FROM api_keys WHERE user_id = :user_id")
                    result = conn.execute(query, {"user_id": user_id}).fetchone()
                    
                    if not result:
                        print("   ❌ No API keys found")
                        continue
                        
                    api_key = security_manager.decrypt(result.encrypted_api_key)
                    api_secret = security_manager.decrypt(result.encrypted_api_secret)
                    exchange_name = result.exchange
                    is_testnet = result.is_testnet
                
                # Initialize adapter - start with futures=False for safer default
                adapter = CCXTAdapter(
                    api_key=api_key,
                    api_secret=api_secret,
                    exchange_name=exchange_name,
                    testnet=is_testnet,
                    futures=False  # Start with spot/margin mode
                )
                
                try:
                    positions = []
                    total_margin_used = 0.0
                    total_unrealized_pnl = 0.0
                    account_type = "SPOT"
                    
                    # --- TRY FUTURES FIRST (if available) ---
                    futures_error = None
                    try:
                        adapter.exchange.options['defaultType'] = 'future'
                        positions_raw = await adapter.exchange.fetch_positions()
                        positions = [
                            Position(
                                symbol=pos['symbol'],
                                side=pos['side'] or 'long',
                                quantity=float(pos.get('contracts') or 0),
                                entry_price=float(pos.get('entryPrice') or pos.get('markPrice') or 0.0),
                                unrealized_pnl=float(pos.get('unrealizedPnl') or 0),
                                leverage=float(pos.get('leverage') or 1)
                            ) for pos in positions_raw if pos.get('contracts') and float(pos['contracts']) > 0
                        ]
                        if positions:
                            account_type = "FUTURES"
                    except Exception as e:
                        futures_error = str(e)
                        # Reset to spot mode
                        adapter.exchange.options['defaultType'] = 'spot'
                    
                    # --- TRY MARGIN if no Futures positions ---
                    margin_balance = {}
                    margin_positions_info = []
                    if not positions:
                        try:
                            adapter.exchange.options['defaultType'] = 'margin'
                            margin_balance = await adapter.exchange.fetch_balance({'type': 'margin'})
                            
                            # For Binance margin - check for borrowed assets (indicates positions)
                            margin_total = margin_balance.get('total', {})
                            margin_used_assets = margin_balance.get('used', {})
                            
                            # Find assets with non-zero balances in margin
                            for asset, amount in margin_total.items():
                                if amount and float(amount) > 0.0001:
                                    borrowed = float(margin_used_assets.get(asset, 0) or 0)
                                    if borrowed > 0 or asset not in ['USDT', 'USDC', 'USD']:
                                        margin_positions_info.append({
                                            'asset': asset,
                                            'total': float(amount),
                                            'borrowed': borrowed
                                        })
                            
                            if margin_positions_info:
                                account_type = "MARGIN"
                        except Exception as e:
                            # Margin not available
                            pass
                    
                    # --- DISPLAY POSITIONS ---
                    if positions:
                        print(f"   📉 {account_type} POSITIONS:")
                        for p in positions:
                            try:
                                ticker = await adapter.exchange.fetch_ticker(p.symbol)
                                current_price = ticker['last']
                                position_value = p.quantity * current_price
                                margin_used = position_value / p.leverage if p.leverage > 0 else position_value
                                total_margin_used += margin_used
                                total_unrealized_pnl += p.unrealized_pnl
                                
                                print(f"      🔹 {p.symbol:<12} {p.side.upper():<5} {p.quantity:>10.4f} | Lev: {p.leverage:>2.0f}x | PnL: {p.unrealized_pnl:>8.2f} | Margin: {margin_used:>8.2f}")
                            except Exception:
                                print(f"      🔹 {p.symbol:<12} {p.side.upper():<5} {p.quantity:>10.4f} | Lev: {p.leverage:>2.0f}x | PnL: {p.unrealized_pnl:>8.2f}")
                        
                        print(f"      ----------------------------------------------------------------")
                        print(f"      📊 Total PnL:         {total_unrealized_pnl:>8.2f}")
                        print(f"      🔒 Total Margin Used: {total_margin_used:>8.2f}")
                    
                    elif margin_positions_info:
                        print(f"   📉 {account_type} ASSETS:")
                        for mp in margin_positions_info:
                            borrowed_str = f" (borrowed: {mp['borrowed']:.4f})" if mp['borrowed'] > 0 else ""
                            print(f"      🔹 {mp['asset']:<6}: {mp['total']:>12.6f}{borrowed_str}")
                    
                    elif futures_error and "-2015" in futures_error:
                        print(f"   📉 POSITIONS: Futures N/A (no API permissions)")
                    else:
                        print(f"   📉 POSITIONS: None")

                    # --- BALANCE SECTION ---
                    # Reset to spot mode for balance fetch
                    adapter.exchange.options['defaultType'] = 'spot'
                    
                    # Fetch SPOT balance
                    spot_balance = await adapter.exchange.fetch_balance()
                    spot_total = spot_balance.get('total', {})
                    
                    # Also try to get margin balance for users with margin accounts
                    margin_total = {}
                    if account_type == "MARGIN" or margin_balance:
                        margin_total = margin_balance.get('total', {}) if margin_balance else {}
                    
                    # Combine balances (prefer margin if available)
                    combined_balance = {}
                    for asset in set(list(spot_total.keys()) + list(margin_total.keys())):
                        spot_amt = float(spot_total.get(asset, 0) or 0)
                        margin_amt = float(margin_total.get(asset, 0) or 0)
                        total_amt = spot_amt + margin_amt
                        if total_amt > 0.0001:
                            combined_balance[asset] = {
                                'spot': spot_amt,
                                'margin': margin_amt,
                                'total': total_amt
                            }
                    
                    print(f"\n   💰 WALLET ({account_type}):")
                    if combined_balance:
                        for asset, amounts in combined_balance.items():
                            if amounts['total'] > 0.0001:
                                location = ""
                                if amounts['margin'] > 0 and amounts['spot'] > 0:
                                    location = f" (spot: {amounts['spot']:.4f}, margin: {amounts['margin']:.4f})"
                                elif amounts['margin'] > 0:
                                    location = " [margin]"
                                print(f"      💵 {asset:<6}: {amounts['total']:>12.4f}{location}")
                    else:
                        print("      (Empty)")
                        
                    # Calculate approximate Equity
                    usdt_bal = combined_balance.get('USDT', {}).get('total', 0)
                    usd_bal = combined_balance.get('USD', {}).get('total', 0)
                    usdc_bal = combined_balance.get('USDC', {}).get('total', 0)
                    
                    # Assuming 1:1 peg for simplicity in this view
                    stable_equity = usdt_bal + usd_bal + usdc_bal
                    total_equity = stable_equity + total_unrealized_pnl
                    free_margin = total_equity - total_margin_used
                    
                    print(f"\n   🧮 ACCOUNT SUMMARY (Est.):")
                    print(f"      💵 Stable Balance:    {stable_equity:>8.2f} (USDT/USD/USDC)")
                    print(f"      📈 Total Equity:      {total_equity:>8.2f}")
                    print(f"      🔓 Free Margin:       {free_margin:>8.2f}")
                    
                    # --- MONTHLY P&L SECTION ---
                    # Try Supabase API first (more realtime), fallback to SQLAlchemy
                    if supabase_client:
                        monthly_stats = await get_monthly_pnl_from_supabase(supabase_client, user_id)
                    else:
                        monthly_stats = await get_monthly_pnl_from_db(engine, user_id)
                    
                    print(f"\n   📅 MONTHLY P&L (Last 30 days):")
                    if monthly_stats['trade_count'] > 0:
                        pnl_color = "🟢" if monthly_stats['total_pnl'] >= 0 else "🔴"
                        print(f"      {pnl_color} Realized P&L:     {monthly_stats['total_pnl']:>+10.2f} USDT")
                        print(f"      📊 Closed Trades:     {monthly_stats['trade_count']:>10}")
                        print(f"      ✅ Winning:           {monthly_stats['winning_trades']:>10} ({monthly_stats['win_rate']:.1f}%)")
                        print(f"      ❌ Losing:            {monthly_stats['losing_trades']:>10}")
                        if monthly_stats['avg_win'] > 0:
                            print(f"      📈 Avg Win:           {monthly_stats['avg_win']:>+10.2f}")
                        if monthly_stats['avg_loss'] < 0:
                            print(f"      📉 Avg Loss:          {monthly_stats['avg_loss']:>+10.2f}")
                        if monthly_stats['best_trade'] > 0:
                            print(f"      🏆 Best Trade:        {monthly_stats['best_trade']:>+10.2f}")
                        if monthly_stats['worst_trade'] < 0:
                            print(f"      💀 Worst Trade:       {monthly_stats['worst_trade']:>+10.2f}")
                        
                        # Show recent closed trades
                        if monthly_stats['recent_trades']:
                            print(f"\n   📜 RECENT CLOSED TRADES:")
                            for i, trade in enumerate(monthly_stats['recent_trades'][:10], 1):
                                pnl_icon = "🟢" if trade['pnl'] >= 0 else "🔴"
                                reason_str = trade.get('reason') or 'unknown'
                                reason_icon = {
                                    'stop_loss': '🛑 SL',
                                    'sl_triggered': '🛑 SL',
                                    'take_profit': '🎯 TP',
                                    'tp_triggered': '🎯 TP',
                                    'trailing_stop': '📈 TS',
                                    'trailing': '📈 TS',
                                    'manual': '✋',
                                    'normal': '✅',
                                    'time_exit': '⏰',
                                    'liquidation_protection': '🚨',
                                    'auto_close_liquidation': '🚨',
                                    'ghost_cleanup': '👻',
                                    'closed': '✅',
                                    'unknown': '❓'
                                }.get(reason_str.lower() if reason_str else 'unknown', reason_str[:6] if reason_str else '❓')
                                
                                # Format date
                                closed_str = ""
                                if trade.get('closed_at'):
                                    try:
                                        if isinstance(trade['closed_at'], str):
                                            closed_str = trade['closed_at'][:16].replace('T', ' ')
                                        else:
                                            closed_str = trade['closed_at'].strftime('%m-%d %H:%M')
                                    except:
                                        closed_str = str(trade['closed_at'])[:16]
                                
                                # Format numbers
                                entry_str = f"{trade.get('entry', 0):.2f}" if trade.get('entry', 0) < 10000 else f"{trade.get('entry', 0):.0f}"
                                exit_str = f"{trade.get('exit', 0):.2f}" if trade.get('exit', 0) < 10000 else f"{trade.get('exit', 0):.0f}"
                                
                                print(f"      {i:>2}. {pnl_icon} {trade['symbol']:<12} {str(trade.get('side', 'buy')):<5} | {entry_str} → {exit_str} | PnL: {trade['pnl']:>+8.2f} | {reason_icon} | {closed_str}")
                    else:
                        print(f"      ⚪ No closed trades in last 30 days")
                    
                    # Aggregate stats
                    total_equity_all += total_equity
                    total_pnl_all += total_unrealized_pnl
                    total_monthly_pnl_all += monthly_stats['total_pnl']
                    total_monthly_trades_all += monthly_stats['trade_count']
                    active_users += 1
                    
                except Exception as e:
                    print(f"   ❌ Exchange Error: {e}")
                finally:
                    await adapter.close()
            
            except Exception as e:
                print(f"   ❌ System/DB Error for user {user_id}: {e}")
                # Continue to next user
                continue
        
        # Global summary
        print(f"\n{'='*70}")
        print(f"📊 GLOBAL SUMMARY - ALL USERS")
        print(f"{'='*70}")
        print(f"   👥 Total Users Checked:     {len(users)}")
        print(f"   ✅ Active Users (connected): {active_users}")
        print(f"   💰 Combined Equity:         {total_equity_all:>12.2f} USDT")
        print(f"   📈 Combined Unrealized PnL: {total_pnl_all:>12.2f} USDT")
        print(f"\n   📅 MONTHLY STATISTICS (Last 30 days):")
        monthly_color = "🟢" if total_monthly_pnl_all >= 0 else "🔴"
        print(f"   {monthly_color} Realized P&L (closed):  {total_monthly_pnl_all:>+12.2f} USDT")
        print(f"   📊 Total Closed Trades:      {total_monthly_trades_all:>12}")
        
        # Combined P&L (realized + unrealized)
        combined_pnl = total_monthly_pnl_all + total_pnl_all
        combined_color = "🟢" if combined_pnl >= 0 else "🔴"
        print(f"\n   {combined_color} TOTAL P&L (realized + unrealized): {combined_pnl:>+12.2f} USDT")
        print(f"{'='*70}")
        
        print("\n⏳ Waiting 60 seconds...")
        await asyncio.sleep(60)

if __name__ == "__main__":
    print("="*70)
    print("  🤖 ASE BOT - ALL USERS MONITOR")
    print("  📊 Monitoring ALL users from database")
    print("  ⏰ Refresh interval: 60 seconds")
    print("  🛑 Press Ctrl+C to stop")
    print("="*70)
    asyncio.run(monitor_group())
