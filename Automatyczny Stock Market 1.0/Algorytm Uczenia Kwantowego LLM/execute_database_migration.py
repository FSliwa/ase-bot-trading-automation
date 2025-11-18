#!/usr/bin/env python3
"""
Database Migration Executor
Simple SQLite-based migration executor for the trading system
"""

import sqlite3
import os
import sys
from datetime import datetime
from typing import List, Dict, Any
import logging
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SimpleDatabaseMigrator:
    def __init__(self, db_path: str = "../trading.db"):
        self.db_path = db_path
        self.migrations_executed = []
        
    def connect(self):
        """Create database connection"""
        return sqlite3.connect(self.db_path)
    
    def ensure_migration_table(self):
        """Ensure migration tracking table exists"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS database_migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    migration_name TEXT NOT NULL UNIQUE,
                    executed_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed'
                )
            """)
            conn.commit()
    
    def is_migration_executed(self, migration_name: str) -> bool:
        """Check if migration was already executed"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM database_migrations WHERE migration_name = ? AND status = 'completed'",
                (migration_name,)
            )
            return cursor.fetchone()[0] > 0
    
    def mark_migration_executed(self, migration_name: str):
        """Mark migration as executed"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO database_migrations (migration_name, executed_at) VALUES (?, ?)",
                (migration_name, datetime.now().isoformat())
            )
            conn.commit()
    
    def execute_migration_01_market_data_partitioning(self):
        """Migration 01: Market Data Partitioning"""
        migration_name = "01_market_data_partitioning"
        if self.is_migration_executed(migration_name):
            logger.info(f"Migration {migration_name} already executed, skipping")
            return
        
        logger.info(f"Executing migration: {migration_name}")
        
        with self.connect() as conn:
            cursor = conn.cursor()
            
            # Create partitioned market data table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_data_partitioned (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL,
                    bid REAL,
                    ask REAL,
                    spread REAL,
                    source TEXT,
                    partition_date TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_data_symbol_timestamp ON market_data_partitioned(symbol, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_data_partition_date ON market_data_partitioned(partition_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_data_price ON market_data_partitioned(price)")
            
            conn.commit()
        
        self.mark_migration_executed(migration_name)
        logger.info(f"Migration {migration_name} completed successfully")
    
    def execute_migration_02_portfolio_snapshots(self):
        """Migration 02: Portfolio Snapshots"""
        migration_name = "02_portfolio_snapshots"
        if self.is_migration_executed(migration_name):
            logger.info(f"Migration {migration_name} already executed, skipping")
            return
        
        logger.info(f"Executing migration: {migration_name}")
        
        with self.connect() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    snapshot_date TEXT NOT NULL,
                    total_value REAL NOT NULL,
                    cash_balance REAL NOT NULL,
                    positions_value REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    day_change REAL,
                    day_change_percent REAL,
                    positions_json TEXT,
                    metrics_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_user_date ON portfolio_snapshots(user_id, snapshot_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date ON portfolio_snapshots(snapshot_date)")
            
            conn.commit()
        
        self.mark_migration_executed(migration_name)
        logger.info(f"Migration {migration_name} completed successfully")
    
    def execute_migration_03_trading_metrics_cache(self):
        """Migration 03: Trading Metrics Cache"""
        migration_name = "03_trading_metrics_cache"
        if self.is_migration_executed(migration_name):
            logger.info(f"Migration {migration_name} already executed, skipping")
            return
        
        logger.info(f"Executing migration: {migration_name}")
        
        with self.connect() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_metrics_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    metric_type TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    calculated_at TEXT NOT NULL,
                    value REAL NOT NULL,
                    metadata_json TEXT,
                    expires_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trading_metrics_user_type ON trading_metrics_cache(user_id, metric_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trading_metrics_expires ON trading_metrics_cache(expires_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trading_metrics_timeframe ON trading_metrics_cache(timeframe)")
            
            conn.commit()
        
        self.mark_migration_executed(migration_name)
        logger.info(f"Migration {migration_name} completed successfully")
    
    def execute_migration_04_audit_logs(self):
        """Migration 04: Audit Logs"""
        migration_name = "04_audit_logs"
        if self.is_migration_executed(migration_name):
            logger.info(f"Migration {migration_name} already executed, skipping")
            return
        
        logger.info(f"Executing migration: {migration_name}")
        
        with self.connect() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER,
                    old_values_json TEXT,
                    new_values_json TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    session_id TEXT,
                    timestamp TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_user_timestamp ON audit_logs(user_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)")
            
            conn.commit()
        
        self.mark_migration_executed(migration_name)
        logger.info(f"Migration {migration_name} completed successfully")
    
    def execute_migration_05_security_events(self):
        """Migration 05: Security Events"""
        migration_name = "05_security_events"
        if self.is_migration_executed(migration_name):
            logger.info(f"Migration {migration_name} already executed, skipping")
            return
        
        logger.info(f"Executing migration: {migration_name}")
        
        with self.connect() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    user_id INTEGER,
                    ip_address TEXT,
                    user_agent TEXT,
                    endpoint TEXT,
                    payload_json TEXT,
                    risk_score REAL,
                    blocked BOOLEAN DEFAULT FALSE,
                    resolved BOOLEAN DEFAULT FALSE,
                    timestamp TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_security_events_type_timestamp ON security_events(event_type, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_security_events_severity ON security_events(severity)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_security_events_user ON security_events(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_security_events_blocked ON security_events(blocked)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_security_events_resolved ON security_events(resolved)")
            
            conn.commit()
        
        self.mark_migration_executed(migration_name)
        logger.info(f"Migration {migration_name} completed successfully")
    
    def execute_migration_06_risk_limits(self):
        """Migration 06: Risk Limits"""
        migration_name = "06_risk_limits"
        if self.is_migration_executed(migration_name):
            logger.info(f"Migration {migration_name} already executed, skipping")
            return
        
        logger.info(f"Executing migration: {migration_name}")
        
        with self.connect() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS risk_limits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    limit_type TEXT NOT NULL,
                    limit_value REAL NOT NULL,
                    current_value REAL DEFAULT 0,
                    utilization_percent REAL DEFAULT 0,
                    soft_limit REAL,
                    hard_limit REAL,
                    breached BOOLEAN DEFAULT FALSE,
                    breach_count INTEGER DEFAULT 0,
                    last_breach_at TEXT,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_risk_limits_user_type ON risk_limits(user_id, limit_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_risk_limits_breached ON risk_limits(breached)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_risk_limits_active ON risk_limits(active)")
            
            conn.commit()
        
        self.mark_migration_executed(migration_name)
        logger.info(f"Migration {migration_name} completed successfully")
    
    def execute_migration_07_ai_model_versions(self):
        """Migration 07: AI Model Versions"""
        migration_name = "07_ai_model_versions"
        if self.is_migration_executed(migration_name):
            logger.info(f"Migration {migration_name} already executed, skipping")
            return
        
        logger.info(f"Executing migration: {migration_name}")
        
        with self.connect() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_model_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    model_type TEXT NOT NULL,
                    parameters_json TEXT,
                    performance_metrics_json TEXT,
                    training_data_hash TEXT,
                    accuracy REAL,
                    precision_score REAL,
                    recall REAL,
                    f1_score REAL,
                    active BOOLEAN DEFAULT FALSE,
                    deployed_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_model_name_version ON ai_model_versions(model_name, version)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_model_active ON ai_model_versions(active)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_model_type ON ai_model_versions(model_type)")
            
            # Create signal performance tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signal_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    model_version_id INTEGER,
                    symbol TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    predicted_direction TEXT NOT NULL,
                    predicted_price REAL,
                    actual_price REAL,
                    actual_direction TEXT,
                    accuracy BOOLEAN,
                    profit_loss REAL,
                    signal_timestamp TEXT NOT NULL,
                    evaluation_timestamp TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (model_version_id) REFERENCES ai_model_versions (id)
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signal_performance_model ON signal_performance(model_version_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signal_performance_symbol ON signal_performance(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signal_performance_timestamp ON signal_performance(signal_timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signal_performance_accuracy ON signal_performance(accuracy)")
            
            conn.commit()
        
        self.mark_migration_executed(migration_name)
        logger.info(f"Migration {migration_name} completed successfully")
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get status of all migrations"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT migration_name, executed_at, status FROM database_migrations ORDER BY executed_at")
            migrations = cursor.fetchall()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [table[0] for table in cursor.fetchall()]
            
            return {
                "executed_migrations": [
                    {"name": m[0], "executed_at": m[1], "status": m[2]} 
                    for m in migrations
                ],
                "total_tables": len(tables),
                "tables": tables,
                "database_size": os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            }
    
    def run_all_migrations(self):
        """Execute all migrations in order"""
        logger.info("Starting database migration process...")
        
        # Ensure migration tracking table exists
        self.ensure_migration_table()
        
        # Execute all migrations in order
        migrations = [
            self.execute_migration_01_market_data_partitioning,
            self.execute_migration_02_portfolio_snapshots,
            self.execute_migration_03_trading_metrics_cache,
            self.execute_migration_04_audit_logs,
            self.execute_migration_05_security_events,
            self.execute_migration_06_risk_limits,
            self.execute_migration_07_ai_model_versions
        ]
        
        for migration in migrations:
            try:
                migration()
            except Exception as e:
                logger.error(f"Migration failed: {migration.__name__}: {str(e)}")
                raise
        
        # Get final status
        status = self.get_migration_status()
        logger.info("Migration process completed successfully!")
        logger.info(f"Total tables: {status['total_tables']}")
        logger.info(f"Executed migrations: {len(status['executed_migrations'])}")
        
        return status

def main():
    """Main execution function"""
    print("🔄 Starting Database Migration Process...")
    print("=" * 60)
    
    migrator = SimpleDatabaseMigrator()
    
    try:
        # Check if database exists
        if not os.path.exists(migrator.db_path):
            print(f"❌ Database file not found: {migrator.db_path}")
            return False
        
        # Run migrations
        status = migrator.run_all_migrations()
        
        print("\n✅ Migration Process Completed Successfully!")
        print("=" * 60)
        print(f"📊 Database Status:")
        print(f"   • Total Tables: {status['total_tables']}")
        print(f"   • Executed Migrations: {len(status['executed_migrations'])}")
        print(f"   • Database Size: {status['database_size'] / (1024*1024):.2f} MB")
        
        print(f"\n📋 New Tables Created:")
        new_tables = [
            'market_data_partitioned', 'portfolio_snapshots', 'trading_metrics_cache',
            'audit_logs', 'security_events', 'risk_limits', 'ai_model_versions', 'signal_performance'
        ]
        for table in new_tables:
            if table in status['tables']:
                print(f"   ✅ {table}")
            else:
                print(f"   ❌ {table}")
        
        print(f"\n📝 Migration Log:")
        for migration in status['executed_migrations']:
            print(f"   • {migration['name']} - {migration['executed_at']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        logger.error(f"Migration process failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
