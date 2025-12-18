"""
Database Migration: Add source field to positions table

This migration adds the 'source' field to track whether a position
was opened by the bot ('bot') or manually by the user ('manual').

Positions with source='manual' will NOT be auto-managed by the bot.

Run this migration before starting the bot to ensure manual positions
are properly protected from bot interference.

Usage:
    python migrations/add_position_source.py

Author: ASE BOT Trading System
Date: 2025-12-15
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from bot.db import DATABASE_URL


def run_migration():
    """Add source column to positions table."""
    print("=" * 60)
    print("🔧 MIGRATION: Add 'source' field to positions table")
    print("=" * 60)
    
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Check if column already exists
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('positions')]
        
        if 'source' in columns:
            print("✅ Column 'source' already exists - skipping migration")
            return
        
        print("📝 Adding 'source' column to positions table...")
        
        # Add the column with default value 'bot' for existing positions
        # This assumes existing positions were opened by the bot
        conn.execute(text("""
            ALTER TABLE positions 
            ADD COLUMN source VARCHAR(50) DEFAULT 'bot'
        """))
        conn.commit()
        
        print("✅ Column 'source' added successfully")
        
        # Count existing positions
        result = conn.execute(text("SELECT COUNT(*) FROM positions WHERE status = 'OPEN'"))
        open_count = result.scalar()
        
        if open_count > 0:
            print(f"\n⚠️  Found {open_count} existing open positions")
            print("   These are marked as source='bot' by default")
            print("   To mark a position as manual, run:")
            print("   UPDATE positions SET source='manual' WHERE symbol='YOUR_SYMBOL' AND status='OPEN';")
        
        print("\n📋 New source values:")
        print("   - 'bot': Opened by trading bot (will be auto-managed)")
        print("   - 'manual': Opened manually by user (will NOT be auto-managed)")
        print("   - 'unknown': Unknown source (will be auto-managed with caution)")
        print("   - 'external': Opened by external system (will NOT be auto-managed)")


def mark_position_as_manual(symbol: str, user_id: str = None):
    """Helper function to mark a specific position as manual."""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        if user_id:
            query = text("""
                UPDATE positions 
                SET source = 'manual' 
                WHERE symbol = :symbol AND user_id = :user_id AND status = 'OPEN'
            """)
            conn.execute(query, {"symbol": symbol, "user_id": user_id})
        else:
            query = text("""
                UPDATE positions 
                SET source = 'manual' 
                WHERE symbol = :symbol AND status = 'OPEN'
            """)
            conn.execute(query, {"symbol": symbol})
        
        conn.commit()
        print(f"✅ Marked position {symbol} as manual")


def list_positions_by_source():
    """List all open positions grouped by source."""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT symbol, side, source, entry_price, quantity, stop_loss, take_profit
            FROM positions 
            WHERE status = 'OPEN'
            ORDER BY source, symbol
        """))
        
        print("\n📊 Open Positions by Source:")
        print("-" * 80)
        
        current_source = None
        for row in result:
            if row.source != current_source:
                current_source = row.source
                print(f"\n🏷️  Source: {current_source or 'NULL'}")
                print("-" * 40)
            
            sl_str = f"SL={row.stop_loss:.4f}" if row.stop_loss else "NO SL"
            tp_str = f"TP={row.take_profit:.4f}" if row.take_profit else "NO TP"
            print(f"   {row.symbol} | {row.side} | Entry: {row.entry_price:.4f} | Qty: {row.quantity:.6f} | {sl_str} | {tp_str}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Position source migration")
    parser.add_argument("--mark-manual", type=str, help="Mark a symbol as manual position")
    parser.add_argument("--user-id", type=str, help="User ID for mark-manual")
    parser.add_argument("--list", action="store_true", help="List positions by source")
    
    args = parser.parse_args()
    
    if args.list:
        list_positions_by_source()
    elif args.mark_manual:
        mark_position_as_manual(args.mark_manual, args.user_id)
    else:
        run_migration()
        list_positions_by_source()
