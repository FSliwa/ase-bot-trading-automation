#!/usr/bin/env python3
"""Initialize demo data for the trading bot."""

import sys
from datetime import datetime, timedelta
import random

from bot.db import init_db, DatabaseManager, Position, Order, Fill
from bot.broker.enhanced_paper import EnhancedPaperBroker


def create_demo_data():
    """Create demo trading data for visualization."""
    print("Initializing database...")
    init_db()
    
    print("Creating demo broker...")
    broker = EnhancedPaperBroker(initial_balance=50000.0)
    
    # Create some open positions
    print("Creating open positions...")
    positions = [
        ("BTC/USDT", "LONG", 0.05, 43500, 45000, 3),
        ("ETH/USDT", "LONG", 0.5, 2850, 3000, 5),
        ("ADA/USDT", "LONG", 100, 0.65, 0.68, 10),
        ("SOL/USDT", "SHORT", 10, 120, 115, 5),
        ("MATIC/USDT", "LONG", 500, 0.95, 0.98, 8),
        ("DOT/USDT", "LONG", 50, 7.2, 7.5, 5),
        ("LINK/USDT", "LONG", 30, 14.5, 15.2, 3),
    ]
    
    for symbol, side, quantity, entry_price, current_price, leverage in positions:
        try:
            # Create position via broker
            order_id = broker.place_order(
                side="buy" if side == "LONG" else "sell",
                symbol=symbol,
                order_type="market",
                quantity=quantity,
                price=entry_price,
                leverage=leverage
            )
            
            # Update current price for unrealized PnL
            with DatabaseManager() as db:
                position = db.session.query(Position).filter_by(symbol=symbol, status="OPEN").first()
                if position:
                    position.current_price = current_price
                    db.session.commit()
                    
        except Exception as e:
            print(f"Error creating position {symbol}: {e}")
    
    # Create historical fills for performance metrics
    print("Creating historical trades...")
    with DatabaseManager() as db:
        # Generate fills for the last 30 days
        for i in range(100):
            days_ago = random.randint(1, 30)
            timestamp = datetime.now() - timedelta(days=days_ago, hours=random.randint(0, 23))
            
            fill = Fill(
                order_id=f"HIST_{i}",
                symbol=random.choice(["BTC/USDT", "ETH/USDT", "ADA/USDT", "SOL/USDT"]),
                side=random.choice(["buy", "sell"]),
                quantity=random.uniform(0.01, 1.0),
                price=random.uniform(1000, 50000),
                fee=random.uniform(0.1, 10),
                timestamp=timestamp
            )
            db.session.add(fill)
        
        db.session.commit()
    
    # Print summary
    print("\nDemo data created successfully!")
    account_info = broker.get_account_info()
    print(f"Account balance: ${account_info['balance']:,.2f}")
    print(f"Open positions: {len(broker.get_open_positions())}")
    
    with DatabaseManager() as db:
        fills_count = db.session.query(Fill).count()
        print(f"Historical trades: {fills_count}")


if __name__ == "__main__":
    create_demo_data()
