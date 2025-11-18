"""
DATABASE MIGRATION SCRIPTS - ENHANCED SCHEMA IMPLEMENTATION
Migracje bazy danych dla nowych tabel i rozszerzonych schematów
"""

# ==================================================================================
# 🗃️ DATABASE MIGRATION SYSTEM
# ==================================================================================

import asyncio
import asyncpg
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseMigrationManager:
    """
    Zarządzanie migracjami bazy danych z versioning i rollback
    """
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.migrations_dir = Path(__file__).parent / "migrations"
        self.migrations_dir.mkdir(exist_ok=True)
        
    async def create_migration_table(self, conn: asyncpg.Connection):
        """Tworzy tabelę śledzenia migracji"""
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                version VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                rollback_sql TEXT,
                checksum VARCHAR(64)
            )
        """)
        
        logger.info("Migration tracking table created/verified")
    
    async def get_applied_migrations(self, conn: asyncpg.Connection) -> List[str]:
        """Pobiera listę zastosowanych migracji"""
        rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY applied_at")
        return [row['version'] for row in rows]
    
    async def apply_migration(self, conn: asyncpg.Connection, migration: Dict[str, Any]):
        """Aplikuje pojedynczą migrację"""
        version = migration['version']
        name = migration['name']
        sql = migration['up_sql']
        rollback_sql = migration.get('rollback_sql', '')
        
        try:
            logger.info(f"Applying migration {version}: {name}")
            
            # Start transaction for migration
            async with conn.transaction():
                # Execute migration SQL
                await conn.execute(sql)
                
                # Record migration in tracking table
                await conn.execute("""
                    INSERT INTO schema_migrations (version, name, rollback_sql)
                    VALUES ($1, $2, $3)
                """, version, name, rollback_sql)
            
            logger.info(f"Successfully applied migration {version}")
            
        except Exception as e:
            logger.error(f"Failed to apply migration {version}: {str(e)}")
            raise
    
    async def rollback_migration(self, conn: asyncpg.Connection, version: str):
        """Rollback pojedynczej migracji"""
        try:
            # Get rollback SQL
            row = await conn.fetchrow("""
                SELECT name, rollback_sql FROM schema_migrations WHERE version = $1
            """, version)
            
            if not row:
                raise ValueError(f"Migration {version} not found")
            
            if not row['rollback_sql']:
                raise ValueError(f"No rollback SQL available for migration {version}")
            
            logger.info(f"Rolling back migration {version}: {row['name']}")
            
            async with conn.transaction():
                # Execute rollback SQL
                await conn.execute(row['rollback_sql'])
                
                # Remove migration record
                await conn.execute("""
                    DELETE FROM schema_migrations WHERE version = $1
                """, version)
            
            logger.info(f"Successfully rolled back migration {version}")
            
        except Exception as e:
            logger.error(f"Failed to rollback migration {version}: {str(e)}")
            raise

# ==================================================================================
# 📊 MIGRATION DEFINITIONS
# ==================================================================================

MIGRATIONS = [
    {
        "version": "001_add_position_fields",
        "name": "Add new fields to positions table",
        "up_sql": """
            -- Add new fields to positions table
            ALTER TABLE positions 
            ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(50),
            ADD COLUMN IF NOT EXISTS strategy_version VARCHAR(20),
            ADD COLUMN IF NOT EXISTS signal_source VARCHAR(50),
            ADD COLUMN IF NOT EXISTS signal_confidence DECIMAL(5,4),
            ADD COLUMN IF NOT EXISTS risk_score INTEGER CHECK (risk_score BETWEEN 1 AND 10),
            ADD COLUMN IF NOT EXISTS position_heat DECIMAL(8,4),
            ADD COLUMN IF NOT EXISTS correlation_group VARCHAR(50),
            ADD COLUMN IF NOT EXISTS max_loss_limit DECIMAL(15,8),
            ADD COLUMN IF NOT EXISTS position_size_usd DECIMAL(15,2),
            ADD COLUMN IF NOT EXISTS max_profit_reached DECIMAL(15,8),
            ADD COLUMN IF NOT EXISTS max_loss_reached DECIMAL(15,8),
            ADD COLUMN IF NOT EXISTS days_held INTEGER,
            ADD COLUMN IF NOT EXISTS funding_paid_total DECIMAL(15,8),
            ADD COLUMN IF NOT EXISTS exchange_fees_paid DECIMAL(15,8),
            ADD COLUMN IF NOT EXISTS entry_slippage DECIMAL(8,4),
            ADD COLUMN IF NOT EXISTS exit_slippage DECIMAL(8,4),
            ADD COLUMN IF NOT EXISTS entry_spread DECIMAL(8,4),
            ADD COLUMN IF NOT EXISTS exit_spread DECIMAL(8,4),
            ADD COLUMN IF NOT EXISTS average_entry_price DECIMAL(15,8),
            ADD COLUMN IF NOT EXISTS kelly_percentage DECIMAL(5,4),
            ADD COLUMN IF NOT EXISTS expected_return DECIMAL(8,4),
            ADD COLUMN IF NOT EXISTS volatility_estimate DECIMAL(8,4),
            ADD COLUMN IF NOT EXISTS beta_to_market DECIMAL(6,4),
            ADD COLUMN IF NOT EXISTS tags JSONB,
            ADD COLUMN IF NOT EXISTS notes TEXT,
            ADD COLUMN IF NOT EXISTS auto_close_reason VARCHAR(100),
            ADD COLUMN IF NOT EXISTS external_position_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS last_price_update TIMESTAMP,
            ADD COLUMN IF NOT EXISTS created_by VARCHAR(50);
            
            -- Create indexes for new fields
            CREATE INDEX IF NOT EXISTS idx_positions_strategy_id ON positions(strategy_id);
            CREATE INDEX IF NOT EXISTS idx_positions_risk_score ON positions(risk_score);
            CREATE INDEX IF NOT EXISTS idx_positions_correlation_group ON positions(correlation_group);
            CREATE INDEX IF NOT EXISTS idx_positions_signal_source ON positions(signal_source);
            CREATE INDEX IF NOT EXISTS idx_positions_entry_time_status ON positions(entry_time, status);
            CREATE INDEX IF NOT EXISTS idx_positions_tags ON positions USING GIN(tags);
            CREATE INDEX IF NOT EXISTS idx_positions_heat_score ON positions(position_heat) WHERE status = 'OPEN';
        """,
        "rollback_sql": """
            -- Remove added columns from positions table
            ALTER TABLE positions 
            DROP COLUMN IF EXISTS strategy_id,
            DROP COLUMN IF EXISTS strategy_version,
            DROP COLUMN IF EXISTS signal_source,
            DROP COLUMN IF EXISTS signal_confidence,
            DROP COLUMN IF EXISTS risk_score,
            DROP COLUMN IF EXISTS position_heat,
            DROP COLUMN IF EXISTS correlation_group,
            DROP COLUMN IF EXISTS max_loss_limit,
            DROP COLUMN IF EXISTS position_size_usd,
            DROP COLUMN IF EXISTS max_profit_reached,
            DROP COLUMN IF EXISTS max_loss_reached,
            DROP COLUMN IF EXISTS days_held,
            DROP COLUMN IF EXISTS funding_paid_total,
            DROP COLUMN IF EXISTS exchange_fees_paid,
            DROP COLUMN IF EXISTS entry_slippage,
            DROP COLUMN IF EXISTS exit_slippage,
            DROP COLUMN IF EXISTS entry_spread,
            DROP COLUMN IF EXISTS exit_spread,
            DROP COLUMN IF EXISTS average_entry_price,
            DROP COLUMN IF EXISTS kelly_percentage,
            DROP COLUMN IF EXISTS expected_return,
            DROP COLUMN IF EXISTS volatility_estimate,
            DROP COLUMN IF EXISTS beta_to_market,
            DROP COLUMN IF EXISTS tags,
            DROP COLUMN IF EXISTS notes,
            DROP COLUMN IF EXISTS auto_close_reason,
            DROP COLUMN IF EXISTS external_position_id,
            DROP COLUMN IF EXISTS last_price_update,
            DROP COLUMN IF EXISTS created_by;
            
            -- Remove indexes
            DROP INDEX IF EXISTS idx_positions_strategy_id;
            DROP INDEX IF EXISTS idx_positions_risk_score;
            DROP INDEX IF EXISTS idx_positions_correlation_group;
            DROP INDEX IF EXISTS idx_positions_signal_source;
            DROP INDEX IF EXISTS idx_positions_entry_time_status;
            DROP INDEX IF EXISTS idx_positions_tags;
            DROP INDEX IF EXISTS idx_positions_heat_score;
        """
    },
    
    {
        "version": "002_add_order_fields",
        "name": "Add new fields to orders table",
        "up_sql": """
            -- Add new fields to orders table
            ALTER TABLE orders
            ADD COLUMN IF NOT EXISTS exchange_order_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS exchange_client_order_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS exchange_data JSONB,
            ADD COLUMN IF NOT EXISTS sync_status VARCHAR(20) DEFAULT 'PENDING',
            ADD COLUMN IF NOT EXISTS last_sync_attempt TIMESTAMP,
            ADD COLUMN IF NOT EXISTS sync_error_message TEXT,
            ADD COLUMN IF NOT EXISTS parent_order_id BIGINT REFERENCES orders(id),
            ADD COLUMN IF NOT EXISTS order_group_id VARCHAR(50),
            ADD COLUMN IF NOT EXISTS conditional_type VARCHAR(20),
            ADD COLUMN IF NOT EXISTS trigger_price DECIMAL(15,8),
            ADD COLUMN IF NOT EXISTS trailing_amount DECIMAL(15,8),
            ADD COLUMN IF NOT EXISTS trailing_percent DECIMAL(5,4),
            ADD COLUMN IF NOT EXISTS post_only BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS hidden BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS iceberg_qty DECIMAL(15,8),
            ADD COLUMN IF NOT EXISTS time_window_start TIMESTAMP,
            ADD COLUMN IF NOT EXISTS time_window_end TIMESTAMP,
            ADD COLUMN IF NOT EXISTS average_price DECIMAL(15,8),
            ADD COLUMN IF NOT EXISTS commission DECIMAL(15,8),
            ADD COLUMN IF NOT EXISTS commission_asset VARCHAR(10),
            ADD COLUMN IF NOT EXISTS is_maker BOOLEAN,
            ADD COLUMN IF NOT EXISTS quote_order_qty DECIMAL(15,8),
            ADD COLUMN IF NOT EXISTS slippage_bps DECIMAL(8,4),
            ADD COLUMN IF NOT EXISTS reject_reason VARCHAR(200),
            ADD COLUMN IF NOT EXISTS cancel_reason VARCHAR(200),
            ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS max_retries INTEGER DEFAULT 3,
            ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(50),
            ADD COLUMN IF NOT EXISTS signal_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS urgency_level INTEGER CHECK (urgency_level BETWEEN 1 AND 5),
            ADD COLUMN IF NOT EXISTS expected_fill_time INTERVAL,
            ADD COLUMN IF NOT EXISTS created_by VARCHAR(50),
            ADD COLUMN IF NOT EXISTS modified_by VARCHAR(50),
            ADD COLUMN IF NOT EXISTS order_source VARCHAR(50),
            ADD COLUMN IF NOT EXISTS notes TEXT;
            
            -- Create indexes for new fields
            CREATE INDEX IF NOT EXISTS idx_orders_exchange_order_id ON orders(exchange_order_id);
            CREATE INDEX IF NOT EXISTS idx_orders_sync_status ON orders(sync_status);
            CREATE INDEX IF NOT EXISTS idx_orders_strategy_id ON orders(strategy_id);
            CREATE INDEX IF NOT EXISTS idx_orders_signal_id ON orders(signal_id);
            CREATE INDEX IF NOT EXISTS idx_orders_parent_id ON orders(parent_order_id);
            CREATE INDEX IF NOT EXISTS idx_orders_group_id ON orders(order_group_id);
            CREATE INDEX IF NOT EXISTS idx_orders_retry ON orders(next_retry_at) WHERE next_retry_at IS NOT NULL;
        """,
        "rollback_sql": """
            -- Remove added columns from orders table
            ALTER TABLE orders
            DROP COLUMN IF EXISTS exchange_order_id,
            DROP COLUMN IF EXISTS exchange_client_order_id,
            DROP COLUMN IF EXISTS exchange_data,
            DROP COLUMN IF EXISTS sync_status,
            DROP COLUMN IF EXISTS last_sync_attempt,
            DROP COLUMN IF EXISTS sync_error_message,
            DROP COLUMN IF EXISTS parent_order_id,
            DROP COLUMN IF EXISTS order_group_id,
            DROP COLUMN IF EXISTS conditional_type,
            DROP COLUMN IF EXISTS trigger_price,
            DROP COLUMN IF EXISTS trailing_amount,
            DROP COLUMN IF EXISTS trailing_percent,
            DROP COLUMN IF EXISTS post_only,
            DROP COLUMN IF EXISTS hidden,
            DROP COLUMN IF EXISTS iceberg_qty,
            DROP COLUMN IF EXISTS time_window_start,
            DROP COLUMN IF EXISTS time_window_end,
            DROP COLUMN IF EXISTS average_price,
            DROP COLUMN IF EXISTS commission,
            DROP COLUMN IF EXISTS commission_asset,
            DROP COLUMN IF EXISTS is_maker,
            DROP COLUMN IF EXISTS quote_order_qty,
            DROP COLUMN IF EXISTS slippage_bps,
            DROP COLUMN IF EXISTS reject_reason,
            DROP COLUMN IF EXISTS cancel_reason,
            DROP COLUMN IF EXISTS retry_count,
            DROP COLUMN IF EXISTS max_retries,
            DROP COLUMN IF EXISTS next_retry_at,
            DROP COLUMN IF EXISTS strategy_id,
            DROP COLUMN IF EXISTS signal_id,
            DROP COLUMN IF EXISTS urgency_level,
            DROP COLUMN IF EXISTS expected_fill_time,
            DROP COLUMN IF EXISTS created_by,
            DROP COLUMN IF EXISTS modified_by,
            DROP COLUMN IF EXISTS order_source,
            DROP COLUMN IF EXISTS notes;
            
            -- Remove indexes
            DROP INDEX IF EXISTS idx_orders_exchange_order_id;
            DROP INDEX IF EXISTS idx_orders_sync_status;
            DROP INDEX IF EXISTS idx_orders_strategy_id;
            DROP INDEX IF EXISTS idx_orders_signal_id;
            DROP INDEX IF EXISTS idx_orders_parent_id;
            DROP INDEX IF EXISTS idx_orders_group_id;
            DROP INDEX IF EXISTS idx_orders_retry;
        """
    },
    
    {
        "version": "003_create_market_data_tables",
        "name": "Create market data tables with partitioning",
        "up_sql": """
            -- Create market_data_1m table with partitioning
            CREATE TABLE IF NOT EXISTS market_data_1m (
                id BIGSERIAL,
                symbol VARCHAR(20) NOT NULL,
                exchange VARCHAR(20) NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                open_price DECIMAL(15,8) NOT NULL,
                high_price DECIMAL(15,8) NOT NULL,
                low_price DECIMAL(15,8) NOT NULL,
                close_price DECIMAL(15,8) NOT NULL,
                volume DECIMAL(15,8) NOT NULL,
                quote_volume DECIMAL(15,8),
                trade_count INTEGER,
                vwap DECIMAL(15,8),
                spread_bps DECIMAL(8,4),
                liquidity_score DECIMAL(5,2),
                volatility DECIMAL(8,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                PRIMARY KEY (timestamp, symbol, exchange)
            ) PARTITION BY RANGE (timestamp);
            
            -- Create current month partition
            CREATE TABLE IF NOT EXISTS market_data_1m_current PARTITION OF market_data_1m
            FOR VALUES FROM (date_trunc('month', CURRENT_DATE)) TO (date_trunc('month', CURRENT_DATE) + INTERVAL '1 month');
            
            -- Create next month partition
            CREATE TABLE IF NOT EXISTS market_data_1m_next PARTITION OF market_data_1m
            FOR VALUES FROM (date_trunc('month', CURRENT_DATE) + INTERVAL '1 month') TO (date_trunc('month', CURRENT_DATE) + INTERVAL '2 months');
            
            -- Create indexes
            CREATE INDEX IF NOT EXISTS idx_market_data_1m_symbol_timestamp ON market_data_1m (symbol, timestamp);
            CREATE INDEX IF NOT EXISTS idx_market_data_1m_exchange_timestamp ON market_data_1m (exchange, timestamp);
            CREATE INDEX IF NOT EXISTS idx_market_data_1m_close_price ON market_data_1m (close_price);
            CREATE INDEX IF NOT EXISTS idx_market_data_1m_volume ON market_data_1m (volume);
            
            -- Create current tickers table
            CREATE TABLE IF NOT EXISTS market_tickers (
                symbol VARCHAR(20) PRIMARY KEY,
                exchange VARCHAR(20) NOT NULL,
                bid DECIMAL(15,8),
                ask DECIMAL(15,8),
                last DECIMAL(15,8),
                volume_24h DECIMAL(15,8),
                change_24h DECIMAL(8,4),
                change_24h_percent DECIMAL(6,4),
                high_24h DECIMAL(15,8),
                low_24h DECIMAL(15,8),
                vwap_24h DECIMAL(15,8),
                open_24h DECIMAL(15,8),
                count_24h INTEGER,
                spread_bps DECIMAL(8,4),
                liquidity_tier INTEGER,
                market_cap_rank INTEGER,
                timestamp TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                CONSTRAINT valid_prices CHECK (bid > 0 AND ask > 0 AND last > 0)
            );
            
            CREATE INDEX IF NOT EXISTS idx_market_tickers_exchange ON market_tickers (exchange);
            CREATE INDEX IF NOT EXISTS idx_market_tickers_volume ON market_tickers (volume_24h DESC);
            CREATE INDEX IF NOT EXISTS idx_market_tickers_change ON market_tickers (change_24h_percent DESC);
            CREATE INDEX IF NOT EXISTS idx_market_tickers_updated ON market_tickers (updated_at);
        """,
        "rollback_sql": """
            -- Drop market data tables
            DROP TABLE IF EXISTS market_data_1m CASCADE;
            DROP TABLE IF EXISTS market_tickers CASCADE;
        """
    },
    
    {
        "version": "004_create_performance_tables",
        "name": "Create performance optimization tables",
        "up_sql": """
            -- Create position_snapshots table
            CREATE TABLE IF NOT EXISTS position_snapshots (
                id BIGSERIAL PRIMARY KEY,
                position_id BIGINT NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
                snapshot_time TIMESTAMP NOT NULL,
                price DECIMAL(15,8) NOT NULL,
                unrealized_pnl DECIMAL(15,8),
                realized_pnl DECIMAL(15,8),
                margin_used DECIMAL(15,8),
                portfolio_percentage DECIMAL(6,4),
                risk_score INTEGER,
                funding_rate DECIMAL(8,6),
                mark_price DECIMAL(15,8),
                index_price DECIMAL(15,8),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                UNIQUE(position_id, snapshot_time)
            );
            
            CREATE INDEX IF NOT EXISTS idx_position_snapshots_position_time ON position_snapshots (position_id, snapshot_time);
            CREATE INDEX IF NOT EXISTS idx_position_snapshots_time ON position_snapshots (snapshot_time);
            CREATE INDEX IF NOT EXISTS idx_position_snapshots_pnl ON position_snapshots (unrealized_pnl);
            
            -- Create trading_metrics_cache table
            CREATE TABLE IF NOT EXISTS trading_metrics_cache (
                id BIGSERIAL PRIMARY KEY,
                metric_type VARCHAR(50) NOT NULL,
                symbol VARCHAR(20),
                timeframe VARCHAR(20) NOT NULL,
                value DECIMAL(15,8),
                additional_data JSONB,
                calculation_time TIMESTAMP NOT NULL,
                valid_until TIMESTAMP NOT NULL,
                parameters_hash VARCHAR(64) NOT NULL,
                dependency_list TEXT[],
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                UNIQUE(metric_type, symbol, timeframe, parameters_hash)
            );
            
            CREATE INDEX IF NOT EXISTS idx_trading_metrics_type_symbol ON trading_metrics_cache (metric_type, symbol);
            CREATE INDEX IF NOT EXISTS idx_trading_metrics_valid_until ON trading_metrics_cache (valid_until);
            CREATE INDEX IF NOT EXISTS idx_trading_metrics_timeframe ON trading_metrics_cache (timeframe);
            CREATE INDEX IF NOT EXISTS idx_trading_metrics_hash ON trading_metrics_cache (parameters_hash);
        """,
        "rollback_sql": """
            -- Drop performance tables
            DROP TABLE IF EXISTS trading_metrics_cache CASCADE;
            DROP TABLE IF EXISTS position_snapshots CASCADE;
        """
    },
    
    {
        "version": "005_create_security_tables",
        "name": "Create security and audit tables",
        "up_sql": """
            -- Create audit_logs table with partitioning
            CREATE TABLE IF NOT EXISTS audit_logs (
                id BIGSERIAL,
                user_id VARCHAR(50),
                session_id VARCHAR(100),
                action VARCHAR(100) NOT NULL,
                resource_type VARCHAR(50) NOT NULL,
                resource_id VARCHAR(100),
                old_values JSONB,
                new_values JSONB,
                ip_address INET,
                user_agent TEXT,
                request_id VARCHAR(100),
                api_endpoint VARCHAR(200),
                http_method VARCHAR(10),
                response_status INTEGER,
                execution_time_ms INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                CONSTRAINT valid_http_status CHECK (response_status BETWEEN 100 AND 599)
            ) PARTITION BY RANGE (timestamp);
            
            -- Create current month partition for audit logs
            CREATE TABLE IF NOT EXISTS audit_logs_current PARTITION OF audit_logs
            FOR VALUES FROM (date_trunc('month', CURRENT_DATE)) TO (date_trunc('month', CURRENT_DATE) + INTERVAL '1 month');
            
            -- Create next month partition for audit logs
            CREATE TABLE IF NOT EXISTS audit_logs_next PARTITION OF audit_logs
            FOR VALUES FROM (date_trunc('month', CURRENT_DATE) + INTERVAL '1 month') TO (date_trunc('month', CURRENT_DATE) + INTERVAL '2 months');
            
            CREATE INDEX IF NOT EXISTS idx_audit_logs_user_timestamp ON audit_logs (user_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs (action);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs (resource_type, resource_id);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_ip ON audit_logs (ip_address);
            
            -- Create security_events table
            CREATE TABLE IF NOT EXISTS security_events (
                id BIGSERIAL PRIMARY KEY,
                event_type VARCHAR(50) NOT NULL,
                severity VARCHAR(20) NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
                user_id VARCHAR(50),
                details JSONB NOT NULL,
                ip_address INET,
                user_agent TEXT,
                risk_score INTEGER CHECK (risk_score BETWEEN 1 AND 100),
                automated_response VARCHAR(100),
                manual_review_required BOOLEAN DEFAULT FALSE,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                acknowledged_at TIMESTAMP,
                resolved_at TIMESTAMP,
                false_positive BOOLEAN DEFAULT FALSE,
                resolution_notes TEXT,
                created_by VARCHAR(50) DEFAULT 'system'
            );
            
            CREATE INDEX IF NOT EXISTS idx_security_events_type_severity ON security_events (event_type, severity);
            CREATE INDEX IF NOT EXISTS idx_security_events_user ON security_events (user_id);
            CREATE INDEX IF NOT EXISTS idx_security_events_detected ON security_events (detected_at);
            CREATE INDEX IF NOT EXISTS idx_security_events_unresolved ON security_events (resolved_at) WHERE resolved_at IS NULL;
        """,
        "rollback_sql": """
            -- Drop security tables
            DROP TABLE IF EXISTS security_events CASCADE;
            DROP TABLE IF EXISTS audit_logs CASCADE;
        """
    },
    
    {
        "version": "006_create_portfolio_risk_tables",
        "name": "Create portfolio and risk management tables",
        "up_sql": """
            -- Create portfolio_snapshots table
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id BIGSERIAL PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                snapshot_date DATE NOT NULL,
                total_value DECIMAL(15,2) NOT NULL,
                available_balance DECIMAL(15,2),
                margin_used DECIMAL(15,2),
                margin_available DECIMAL(15,2),
                total_pnl DECIMAL(15,4),
                realized_pnl_today DECIMAL(15,4),
                unrealized_pnl DECIMAL(15,4),
                positions_count INTEGER,
                open_orders_count INTEGER,
                risk_score INTEGER CHECK (risk_score BETWEEN 1 AND 100),
                max_drawdown_30d DECIMAL(8,4),
                sharpe_ratio_30d DECIMAL(6,4),
                allocation_by_symbol JSONB,
                allocation_by_exchange JSONB,
                allocation_by_strategy JSONB,
                leverage_ratio DECIMAL(6,4),
                concentration_risk DECIMAL(6,4),
                correlation_risk DECIMAL(6,4),
                var_95_1d DECIMAL(15,4),
                expected_shortfall DECIMAL(15,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                UNIQUE(user_id, snapshot_date)
            );
            
            CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_user_date ON portfolio_snapshots (user_id, snapshot_date);
            CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_total_value ON portfolio_snapshots (total_value);
            CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_risk_score ON portfolio_snapshots (risk_score);
            
            -- Create risk_limits table
            CREATE TABLE IF NOT EXISTS risk_limits (
                id BIGSERIAL PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                limit_type VARCHAR(50) NOT NULL,
                symbol VARCHAR(20),
                exchange VARCHAR(20),
                strategy_id VARCHAR(50),
                current_value DECIMAL(15,8),
                limit_value DECIMAL(15,8) NOT NULL,
                soft_limit_value DECIMAL(15,8),
                limit_percentage DECIMAL(5,2),
                is_breached BOOLEAN DEFAULT FALSE,
                soft_limit_breached BOOLEAN DEFAULT FALSE,
                breach_count INTEGER DEFAULT 0,
                last_breach_at TIMESTAMP,
                last_check_at TIMESTAMP,
                escalation_level INTEGER DEFAULT 0,
                auto_action VARCHAR(50),
                notification_sent BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                CONSTRAINT valid_limits CHECK (limit_value > 0 AND (soft_limit_value IS NULL OR soft_limit_value <= limit_value)),
                UNIQUE(user_id, limit_type, symbol, exchange, strategy_id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_risk_limits_user_type ON risk_limits (user_id, limit_type);
            CREATE INDEX IF NOT EXISTS idx_risk_limits_breached ON risk_limits (is_breached) WHERE is_breached = TRUE;
            CREATE INDEX IF NOT EXISTS idx_risk_limits_symbol ON risk_limits (symbol) WHERE symbol IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_risk_limits_active ON risk_limits (is_active) WHERE is_active = TRUE;
        """,
        "rollback_sql": """
            -- Drop portfolio and risk tables
            DROP TABLE IF EXISTS risk_limits CASCADE;
            DROP TABLE IF EXISTS portfolio_snapshots CASCADE;
        """
    },
    
    {
        "version": "007_create_ai_analytics_tables",
        "name": "Create AI and analytics tables",
        "up_sql": """
            -- Create ai_model_versions table
            CREATE TABLE IF NOT EXISTS ai_model_versions (
                id BIGSERIAL PRIMARY KEY,
                model_name VARCHAR(100) NOT NULL,
                version VARCHAR(50) NOT NULL,
                model_type VARCHAR(50) NOT NULL,
                deployed_at TIMESTAMP NOT NULL,
                accuracy_score DECIMAL(6,4),
                precision_score DECIMAL(6,4),
                recall_score DECIMAL(6,4),
                f1_score DECIMAL(6,4),
                confidence_threshold DECIMAL(4,3),
                training_data_size INTEGER,
                training_duration INTEGER,
                model_parameters JSONB,
                feature_importance JSONB,
                validation_results JSONB,
                is_active BOOLEAN DEFAULT FALSE,
                rollback_version VARCHAR(50),
                created_by VARCHAR(50),
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                UNIQUE(model_name, version)
            );
            
            CREATE INDEX IF NOT EXISTS idx_ai_model_versions_name_active ON ai_model_versions (model_name, is_active);
            CREATE INDEX IF NOT EXISTS idx_ai_model_versions_deployed ON ai_model_versions (deployed_at);
            CREATE INDEX IF NOT EXISTS idx_ai_model_versions_accuracy ON ai_model_versions (accuracy_score DESC);
            
            -- Create signal_performance table
            CREATE TABLE IF NOT EXISTS signal_performance (
                id BIGSERIAL PRIMARY KEY,
                signal_id VARCHAR(100) NOT NULL,
                signal_type VARCHAR(50) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                model_version VARCHAR(50),
                prediction JSONB NOT NULL,
                confidence DECIMAL(4,3) NOT NULL,
                time_horizon INTEGER NOT NULL,
                actual_outcome JSONB,
                accuracy DECIMAL(6,4),
                profit_impact DECIMAL(10,4),
                risk_impact DECIMAL(8,4),
                market_conditions JSONB,
                created_at TIMESTAMP NOT NULL,
                resolved_at TIMESTAMP,
                resolution_reason VARCHAR(100),
                
                CONSTRAINT valid_confidence CHECK (confidence BETWEEN 0 AND 1),
                CONSTRAINT valid_time_horizon CHECK (time_horizon > 0)
            );
            
            CREATE INDEX IF NOT EXISTS idx_signal_performance_type_symbol ON signal_performance (signal_type, symbol);
            CREATE INDEX IF NOT EXISTS idx_signal_performance_confidence ON signal_performance (confidence DESC);
            CREATE INDEX IF NOT EXISTS idx_signal_performance_accuracy ON signal_performance (accuracy DESC);
            CREATE INDEX IF NOT EXISTS idx_signal_performance_created ON signal_performance (created_at);
            CREATE INDEX IF NOT EXISTS idx_signal_performance_resolved ON signal_performance (resolved_at) WHERE resolved_at IS NOT NULL;
        """,
        "rollback_sql": """
            -- Drop AI analytics tables
            DROP TABLE IF EXISTS signal_performance CASCADE;
            DROP TABLE IF EXISTS ai_model_versions CASCADE;
        """
    }
]

# ==================================================================================
# 🚀 MIGRATION EXECUTION
# ==================================================================================

class MigrationExecutor:
    """
    Wykonuje migracje bazy danych
    """
    
    def __init__(self, database_url: str):
        self.manager = DatabaseMigrationManager(database_url)
    
    async def run_migrations(self):
        """Uruchamia wszystkie oczekujące migracje"""
        conn = await asyncpg.connect(self.manager.database_url)
        
        try:
            # Create migration tracking table
            await self.manager.create_migration_table(conn)
            
            # Get applied migrations
            applied_migrations = await self.manager.get_applied_migrations(conn)
            logger.info(f"Found {len(applied_migrations)} applied migrations")
            
            # Apply pending migrations
            pending_count = 0
            for migration in MIGRATIONS:
                if migration['version'] not in applied_migrations:
                    await self.manager.apply_migration(conn, migration)
                    pending_count += 1
            
            if pending_count == 0:
                logger.info("No pending migrations found - database is up to date")
            else:
                logger.info(f"Successfully applied {pending_count} new migrations")
                
        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            raise
        finally:
            await conn.close()
    
    async def rollback_last_migration(self):
        """Rollback ostatniej migracji"""
        conn = await asyncpg.connect(self.manager.database_url)
        
        try:
            # Get last applied migration
            row = await conn.fetchrow("""
                SELECT version FROM schema_migrations 
                ORDER BY applied_at DESC 
                LIMIT 1
            """)
            
            if not row:
                logger.info("No migrations to rollback")
                return
            
            await self.manager.rollback_migration(conn, row['version'])
            logger.info(f"Successfully rolled back migration {row['version']}")
            
        except Exception as e:
            logger.error(f"Rollback failed: {str(e)}")
            raise
        finally:
            await conn.close()
    
    async def get_migration_status(self):
        """Sprawdza status migracji"""
        conn = await asyncpg.connect(self.manager.database_url)
        
        try:
            await self.manager.create_migration_table(conn)
            applied_migrations = await self.manager.get_applied_migrations(conn)
            
            logger.info(f"\n=== MIGRATION STATUS ===")
            logger.info(f"Applied migrations: {len(applied_migrations)}")
            logger.info(f"Available migrations: {len(MIGRATIONS)}")
            
            pending_migrations = []
            for migration in MIGRATIONS:
                if migration['version'] not in applied_migrations:
                    pending_migrations.append(migration['version'])
            
            if pending_migrations:
                logger.info(f"Pending migrations: {', '.join(pending_migrations)}")
            else:
                logger.info("All migrations are applied - database is up to date")
                
            return {
                'applied': applied_migrations,
                'pending': pending_migrations,
                'total_available': len(MIGRATIONS)
            }
            
        finally:
            await conn.close()

# ==================================================================================
# 📝 USAGE EXAMPLES
# ==================================================================================

async def main():
    """
    Example usage of migration system
    """
    # Database URL from environment or config
    database_url = "postgresql://user:password@localhost:5432/trading_platform"
    
    executor = MigrationExecutor(database_url)
    
    # Check current status
    await executor.get_migration_status()
    
    # Apply all pending migrations
    await executor.run_migrations()
    
    # Check status after migrations
    await executor.get_migration_status()

if __name__ == "__main__":
    asyncio.run(main())
