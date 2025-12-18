"""
Database Optimization Implementation with TimescaleDB
Advanced time-series database optimization for trading data
"""

import asyncio
import asyncpg
import logging
import os
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)

@dataclass
class TimescaleConfig:
    """Configuration for TimescaleDB optimization"""
    # Hypertable settings
    chunk_time_interval: str = "1 day"
    compression_age: str = "7 days"
    retention_period: str = "1 year"
    
    # Performance settings
    max_background_workers: int = 4
    max_parallel_workers_per_gather: int = 2
    effective_cache_size: str = "4GB"  # For 16GB RAM server
    shared_buffers: str = "2GB"
    work_mem: str = "32MB"
    maintenance_work_mem: str = "256MB"
    
    # Connection settings
    max_connections: int = 20
    checkpoint_completion_target: float = 0.9
    wal_buffers: str = "16MB"

class TimescaleDBMigration:
    """Handle migration from PostgreSQL to TimescaleDB"""
    
    def __init__(self, connection_manager):
        self.connection_manager = connection_manager
        self.config = TimescaleConfig()
        self.migration_stats = {
            'tables_migrated': 0,
            'hypertables_created': 0,
            'indexes_optimized': 0,
            'compression_policies_added': 0,
            'retention_policies_added': 0,
            'materialized_views_created': 0,
            'migration_duration': 0.0
        }
    
    async def check_timescale_availability(self) -> bool:
        """Check if TimescaleDB extension is available"""
        try:
            async with self.connection_manager.get_db_connection() as conn:
                result = await conn.fetchrow(
                    "SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'"
                )
                return result is not None
        except Exception as e:
            logger.error(f"Error checking TimescaleDB availability: {str(e)}")
            return False
    
    async def install_timescale_extension(self) -> bool:
        """Install TimescaleDB extension"""
        try:
            async with self.connection_manager.get_db_connection() as conn:
                # Check if already installed
                if await self.check_timescale_availability():
                    logger.info("TimescaleDB extension already installed")
                    return True
                
                # Install extension
                await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
                
                # Verify installation
                if await self.check_timescale_availability():
                    logger.info("TimescaleDB extension installed successfully")
                    return True
                else:
                    logger.error("TimescaleDB extension installation failed")
                    return False
                    
        except Exception as e:
            logger.error(f"Error installing TimescaleDB extension: {str(e)}")
            return False
    
    async def optimize_postgresql_config(self) -> bool:
        """Apply PostgreSQL optimization settings for 16GB RAM server"""
        try:
            async with self.connection_manager.get_db_connection() as conn:
                # Apply memory and performance settings
                config_commands = [
                    f"ALTER SYSTEM SET shared_buffers = '{self.config.shared_buffers}';",
                    f"ALTER SYSTEM SET effective_cache_size = '{self.config.effective_cache_size}';",
                    f"ALTER SYSTEM SET work_mem = '{self.config.work_mem}';",
                    f"ALTER SYSTEM SET maintenance_work_mem = '{self.config.maintenance_work_mem}';",
                    f"ALTER SYSTEM SET max_connections = {self.config.max_connections};",
                    f"ALTER SYSTEM SET checkpoint_completion_target = {self.config.checkpoint_completion_target};",
                    f"ALTER SYSTEM SET wal_buffers = '{self.config.wal_buffers}';",
                    f"ALTER SYSTEM SET max_worker_processes = {self.config.max_background_workers + 8};",
                    f"ALTER SYSTEM SET max_parallel_workers_per_gather = {self.config.max_parallel_workers_per_gather};",
                    
                    # TimescaleDB specific settings
                    "ALTER SYSTEM SET timescaledb.max_background_workers = 4;",
                    "ALTER SYSTEM SET log_statement = 'none';",
                    "ALTER SYSTEM SET log_duration = off;",
                    "ALTER SYSTEM SET log_lock_waits = on;",
                    "ALTER SYSTEM SET log_checkpoints = on;",
                ]
                
                for command in config_commands:
                    try:
                        await conn.execute(command)
                        logger.debug(f"Applied config: {command}")
                    except Exception as e:
                        logger.warning(f"Failed to apply config {command}: {str(e)}")
                
                # Reload configuration
                await conn.execute("SELECT pg_reload_conf();")
                
                logger.info("PostgreSQL configuration optimized for 16GB RAM server")
                return True
                
        except Exception as e:
            logger.error(f"Error optimizing PostgreSQL config: {str(e)}")
            return False
    
    async def create_optimized_hypertables(self) -> List[str]:
        """Create optimized hypertables for time-series data"""
        
        hypertable_definitions = [
            {
                'name': 'market_data_ts',
                'create_sql': '''
                    CREATE TABLE IF NOT EXISTS market_data_ts (
                        id BIGSERIAL,
                        symbol VARCHAR(20) NOT NULL,
                        exchange VARCHAR(20) NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL,
                        price DECIMAL(20,8) NOT NULL,
                        volume DECIMAL(20,8) NOT NULL,
                        high DECIMAL(20,8) NOT NULL,
                        low DECIMAL(20,8) NOT NULL,
                        open DECIMAL(20,8) NOT NULL,
                        close DECIMAL(20,8) NOT NULL,
                        bid DECIMAL(20,8),
                        ask DECIMAL(20,8),
                        spread DECIMAL(20,8),
                        market_cap DECIMAL(20,2),
                        PRIMARY KEY (timestamp, symbol, exchange)
                    );
                ''',
                'time_column': 'timestamp',
                'partitioning_column': 'symbol',
                'chunk_time_interval': self.config.chunk_time_interval
            },
            {
                'name': 'trading_signals_ts',
                'create_sql': '''
                    CREATE TABLE IF NOT EXISTS trading_signals_ts (
                        id BIGSERIAL,
                        symbol VARCHAR(20) NOT NULL,
                        exchange VARCHAR(20) NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL,
                        signal_type VARCHAR(20) NOT NULL,
                        signal_strength DECIMAL(5,4) NOT NULL,
                        price_target DECIMAL(20,8),
                        stop_loss DECIMAL(20,8),
                        confidence_score DECIMAL(5,4),
                        indicator_values JSONB,
                        PRIMARY KEY (timestamp, symbol, exchange, signal_type)
                    );
                ''',
                'time_column': 'timestamp',
                'partitioning_column': 'symbol',
                'chunk_time_interval': self.config.chunk_time_interval
            },
            {
                'name': 'user_portfolio_ts',
                'create_sql': '''
                    CREATE TABLE IF NOT EXISTS user_portfolio_ts (
                        id BIGSERIAL,
                        user_id VARCHAR(50) NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL,
                        total_value DECIMAL(20,8) NOT NULL,
                        total_profit_loss DECIMAL(20,8) NOT NULL,
                        total_profit_loss_percent DECIMAL(8,4) NOT NULL,
                        positions JSONB NOT NULL,
                        performance_metrics JSONB,
                        PRIMARY KEY (timestamp, user_id)
                    );
                ''',
                'time_column': 'timestamp',
                'partitioning_column': 'user_id',
                'chunk_time_interval': "1 hour"  # More frequent snapshots for portfolios
            },
            {
                'name': 'exchange_analytics_ts',
                'create_sql': '''
                    CREATE TABLE IF NOT EXISTS exchange_analytics_ts (
                        id BIGSERIAL,
                        exchange VARCHAR(20) NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL,
                        total_volume_24h DECIMAL(20,8),
                        total_trades_24h BIGINT,
                        active_pairs INTEGER,
                        avg_spread DECIMAL(8,6),
                        uptime_percent DECIMAL(5,2),
                        response_time_ms INTEGER,
                        error_rate DECIMAL(5,4),
                        PRIMARY KEY (timestamp, exchange)
                    );
                ''',
                'time_column': 'timestamp',
                'partitioning_column': 'exchange',
                'chunk_time_interval': "6 hours"
            }
        ]
        
        created_hypertables = []
        
        try:
            async with self.connection_manager.get_db_connection() as conn:
                for table_def in hypertable_definitions:
                    try:
                        # Create table
                        await conn.execute(table_def['create_sql'])
                        logger.info(f"Created table: {table_def['name']}")
                        
                        # Convert to hypertable
                        hypertable_sql = f"""
                            SELECT create_hypertable(
                                '{table_def['name']}', 
                                '{table_def['time_column']}',
                                partitioning_column => '{table_def['partitioning_column']}',
                                chunk_time_interval => INTERVAL '{table_def['chunk_time_interval']}',
                                if_not_exists => TRUE
                            );
                        """
                        
                        await conn.execute(hypertable_sql)
                        logger.info(f"Created hypertable: {table_def['name']}")
                        
                        created_hypertables.append(table_def['name'])
                        self.migration_stats['hypertables_created'] += 1
                        
                    except Exception as e:
                        logger.error(f"Error creating hypertable {table_def['name']}: {str(e)}")
                        continue
            
            return created_hypertables
            
        except Exception as e:
            logger.error(f"Error in hypertable creation: {str(e)}")
            return created_hypertables
    
    async def create_optimized_indexes(self, hypertables: List[str]) -> int:
        """Create optimized indexes for hypertables"""
        
        index_definitions = {
            'market_data_ts': [
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_data_symbol_time ON market_data_ts (symbol, timestamp DESC);",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_data_exchange_time ON market_data_ts (exchange, timestamp DESC);",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_data_price ON market_data_ts (price) WHERE timestamp > NOW() - INTERVAL '24 hours';",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_data_volume ON market_data_ts (volume DESC) WHERE timestamp > NOW() - INTERVAL '24 hours';",
            ],
            'trading_signals_ts': [
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_signals_symbol_type ON trading_signals_ts (symbol, signal_type, timestamp DESC);",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_signals_strength ON trading_signals_ts (signal_strength DESC) WHERE timestamp > NOW() - INTERVAL '24 hours';",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_signals_confidence ON trading_signals_ts (confidence_score DESC);",
            ],
            'user_portfolio_ts': [
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_portfolio_user_time ON user_portfolio_ts (user_id, timestamp DESC);",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_portfolio_performance ON user_portfolio_ts (total_profit_loss_percent DESC);",
            ],
            'exchange_analytics_ts': [
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analytics_exchange_time ON exchange_analytics_ts (exchange, timestamp DESC);",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analytics_volume ON exchange_analytics_ts (total_volume_24h DESC);",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analytics_performance ON exchange_analytics_ts (uptime_percent, response_time_ms);",
            ]
        }
        
        indexes_created = 0
        
        try:
            async with self.connection_manager.get_db_connection() as conn:
                for table_name in hypertables:
                    if table_name in index_definitions:
                        for index_sql in index_definitions[table_name]:
                            try:
                                await conn.execute(index_sql)
                                indexes_created += 1
                                logger.debug(f"Created index on {table_name}")
                            except Exception as e:
                                logger.warning(f"Failed to create index on {table_name}: {str(e)}")
            
            self.migration_stats['indexes_optimized'] = indexes_created
            logger.info(f"Created {indexes_created} optimized indexes")
            return indexes_created
            
        except Exception as e:
            logger.error(f"Error creating indexes: {str(e)}")
            return indexes_created
    
    async def add_compression_policies(self, hypertables: List[str]) -> int:
        """Add compression policies to reduce storage usage"""
        
        policies_added = 0
        
        try:
            async with self.connection_manager.get_db_connection() as conn:
                for table_name in hypertables:
                    try:
                        # Add compression policy (compress data older than configured age)
                        compression_sql = f"""
                            SELECT add_compression_policy('{table_name}', INTERVAL '{self.config.compression_age}');
                        """
                        
                        await conn.execute(compression_sql)
                        policies_added += 1
                        logger.info(f"Added compression policy to {table_name}")
                        
                    except Exception as e:
                        # Policy might already exist
                        if "already exists" not in str(e).lower():
                            logger.warning(f"Failed to add compression policy to {table_name}: {str(e)}")
            
            self.migration_stats['compression_policies_added'] = policies_added
            return policies_added
            
        except Exception as e:
            logger.error(f"Error adding compression policies: {str(e)}")
            return policies_added
    
    async def add_retention_policies(self, hypertables: List[str]) -> int:
        """Add data retention policies"""
        
        policies_added = 0
        
        try:
            async with self.connection_manager.get_db_connection() as conn:
                for table_name in hypertables:
                    try:
                        # Add retention policy (remove data older than configured period)
                        retention_sql = f"""
                            SELECT add_retention_policy('{table_name}', INTERVAL '{self.config.retention_period}');
                        """
                        
                        await conn.execute(retention_sql)
                        policies_added += 1
                        logger.info(f"Added retention policy to {table_name}")
                        
                    except Exception as e:
                        # Policy might already exist
                        if "already exists" not in str(e).lower():
                            logger.warning(f"Failed to add retention policy to {table_name}: {str(e)}")
            
            self.migration_stats['retention_policies_added'] = policies_added
            return policies_added
            
        except Exception as e:
            logger.error(f"Error adding retention policies: {str(e)}")
            return policies_added
    
    async def create_materialized_views(self) -> List[str]:
        """Create materialized views for analytics"""
        
        materialized_views = [
            {
                'name': 'hourly_market_summary',
                'sql': '''
                    CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_market_summary AS
                    SELECT 
                        symbol,
                        exchange,
                        time_bucket('1 hour', timestamp) AS hour,
                        first(price, timestamp) AS open_price,
                        last(price, timestamp) AS close_price,
                        max(high) AS max_price,
                        min(low) AS min_price,
                        sum(volume) AS total_volume,
                        count(*) AS tick_count,
                        avg(spread) AS avg_spread
                    FROM market_data_ts 
                    WHERE timestamp > NOW() - INTERVAL '7 days'
                    GROUP BY symbol, exchange, hour
                    ORDER BY hour DESC;
                '''
            },
            {
                'name': 'daily_portfolio_performance',
                'sql': '''
                    CREATE MATERIALIZED VIEW IF NOT EXISTS daily_portfolio_performance AS
                    SELECT 
                        user_id,
                        time_bucket('1 day', timestamp) AS day,
                        last(total_value, timestamp) AS end_value,
                        first(total_value, timestamp) AS start_value,
                        last(total_profit_loss_percent, timestamp) AS final_pnl_percent,
                        max(total_value) AS max_value,
                        min(total_value) AS min_value
                    FROM user_portfolio_ts 
                    WHERE timestamp > NOW() - INTERVAL '30 days'
                    GROUP BY user_id, day
                    ORDER BY day DESC;
                '''
            },
            {
                'name': 'exchange_performance_metrics',
                'sql': '''
                    CREATE MATERIALIZED VIEW IF NOT EXISTS exchange_performance_metrics AS
                    SELECT 
                        exchange,
                        time_bucket('1 day', timestamp) AS day,
                        avg(total_volume_24h) AS avg_volume,
                        avg(uptime_percent) AS avg_uptime,
                        avg(response_time_ms) AS avg_response_time,
                        avg(error_rate) AS avg_error_rate,
                        sum(total_trades_24h) AS total_trades
                    FROM exchange_analytics_ts 
                    WHERE timestamp > NOW() - INTERVAL '30 days'
                    GROUP BY exchange, day
                    ORDER BY day DESC;
                '''
            },
            {
                'name': 'top_performing_signals',
                'sql': '''
                    CREATE MATERIALIZED VIEW IF NOT EXISTS top_performing_signals AS
                    SELECT 
                        symbol,
                        signal_type,
                        time_bucket('1 day', timestamp) AS day,
                        avg(signal_strength) AS avg_strength,
                        avg(confidence_score) AS avg_confidence,
                        count(*) AS signal_count
                    FROM trading_signals_ts 
                    WHERE timestamp > NOW() - INTERVAL '7 days'
                    AND confidence_score >= 0.7
                    GROUP BY symbol, signal_type, day
                    HAVING count(*) >= 5
                    ORDER BY avg_confidence DESC, avg_strength DESC;
                '''
            }
        ]
        
        created_views = []
        
        try:
            async with self.connection_manager.get_db_connection() as conn:
                for view_def in materialized_views:
                    try:
                        await conn.execute(view_def['sql'])
                        created_views.append(view_def['name'])
                        logger.info(f"Created materialized view: {view_def['name']}")
                        
                        # Create refresh policy for the view
                        refresh_sql = f"""
                            SELECT add_continuous_aggregate_policy(
                                '{view_def['name']}',
                                start_offset => INTERVAL '1 month',
                                end_offset => INTERVAL '1 hour',
                                schedule_interval => INTERVAL '1 hour'
                            );
                        """
                        
                        try:
                            await conn.execute(refresh_sql)
                            logger.info(f"Added continuous aggregate policy for {view_def['name']}")
                        except Exception as e:
                            # Policy might already exist or view might not support it
                            logger.debug(f"Could not add continuous aggregate policy for {view_def['name']}: {str(e)}")
                        
                    except Exception as e:
                        logger.error(f"Error creating materialized view {view_def['name']}: {str(e)}")
                        continue
            
            self.migration_stats['materialized_views_created'] = len(created_views)
            return created_views
            
        except Exception as e:
            logger.error(f"Error creating materialized views: {str(e)}")
            return created_views
    
    async def migrate_existing_data(self, source_tables: List[str], target_hypertables: List[str]) -> bool:
        """Migrate data from existing PostgreSQL tables to hypertables"""
        
        try:
            # Table mapping for migration
            table_mapping = {
                'market_data': 'market_data_ts',
                'trading_signals': 'trading_signals_ts', 
                'user_portfolios': 'user_portfolio_ts',
                'exchange_stats': 'exchange_analytics_ts'
            }
            
            async with self.connection_manager.get_db_connection() as conn:
                for source_table in source_tables:
                    if source_table in table_mapping:
                        target_table = table_mapping[source_table]
                        
                        try:
                            # Check if source table exists
                            exists_check = await conn.fetchrow(
                                "SELECT 1 FROM information_schema.tables WHERE table_name = $1",
                                source_table
                            )
                            
                            if not exists_check:
                                logger.info(f"Source table {source_table} does not exist, skipping migration")
                                continue
                            
                            # Get record count
                            count_result = await conn.fetchrow(f"SELECT COUNT(*) as count FROM {source_table}")
                            total_records = count_result['count'] if count_result else 0
                            
                            if total_records == 0:
                                logger.info(f"No records in {source_table}, skipping migration")
                                continue
                            
                            logger.info(f"Migrating {total_records} records from {source_table} to {target_table}")
                            
                            # Migrate data in batches to avoid memory issues
                            batch_size = 10000
                            offset = 0
                            
                            while offset < total_records:
                                # This is a simplified migration - in practice, you'd need to
                                # map columns appropriately between source and target schemas
                                migration_sql = f"""
                                    INSERT INTO {target_table} 
                                    SELECT * FROM {source_table} 
                                    ORDER BY id 
                                    LIMIT {batch_size} OFFSET {offset}
                                    ON CONFLICT DO NOTHING;
                                """
                                
                                await conn.execute(migration_sql)
                                offset += batch_size
                                
                                logger.info(f"Migrated {min(offset, total_records)}/{total_records} records from {source_table}")
                            
                            self.migration_stats['tables_migrated'] += 1
                            logger.info(f"Successfully migrated {source_table} to {target_table}")
                            
                        except Exception as e:
                            logger.error(f"Error migrating {source_table} to {target_table}: {str(e)}")
                            continue
            
            return True
            
        except Exception as e:
            logger.error(f"Error in data migration: {str(e)}")
            return False
    
    async def run_full_migration(self) -> Dict[str, Any]:
        """Run complete migration process"""
        
        start_time = datetime.now()
        logger.info("Starting TimescaleDB migration process...")
        
        try:
            # Step 1: Install TimescaleDB extension
            if not await self.install_timescale_extension():
                return {
                    'success': False,
                    'error': 'Failed to install TimescaleDB extension',
                    'stats': self.migration_stats
                }
            
            # Step 2: Optimize PostgreSQL configuration
            await self.optimize_postgresql_config()
            
            # Step 3: Create hypertables
            hypertables = await self.create_optimized_hypertables()
            if not hypertables:
                return {
                    'success': False,
                    'error': 'Failed to create hypertables',
                    'stats': self.migration_stats
                }
            
            # Step 4: Create indexes
            await self.create_optimized_indexes(hypertables)
            
            # Step 5: Add compression policies
            await self.add_compression_policies(hypertables)
            
            # Step 6: Add retention policies  
            await self.add_retention_policies(hypertables)
            
            # Step 7: Create materialized views
            materialized_views = await self.create_materialized_views()
            
            # Step 8: Migrate existing data (optional, based on existing tables)
            # await self.migrate_existing_data(['market_data'], hypertables)
            
            # Calculate migration duration
            end_time = datetime.now()
            self.migration_stats['migration_duration'] = (end_time - start_time).total_seconds()
            
            logger.info("TimescaleDB migration completed successfully!")
            
            return {
                'success': True,
                'hypertables_created': hypertables,
                'materialized_views_created': materialized_views,
                'stats': self.migration_stats,
                'migration_duration': self.migration_stats['migration_duration']
            }
            
        except Exception as e:
            end_time = datetime.now()
            self.migration_stats['migration_duration'] = (end_time - start_time).total_seconds()
            
            logger.error(f"TimescaleDB migration failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'stats': self.migration_stats
            }

class TimescaleQueryOptimizer:
    """Optimize queries for TimescaleDB"""
    
    def __init__(self, connection_manager):
        self.connection_manager = connection_manager
    
    async def get_market_data_optimized(self, symbol: str, exchange: str, 
                                      start_time: datetime, end_time: datetime,
                                      interval: str = '1m') -> List[Dict[str, Any]]:
        """Get market data using optimized TimescaleDB queries"""
        
        try:
            async with self.connection_manager.get_db_connection() as conn:
                # Use time_bucket for efficient time-series aggregation
                query = """
                    SELECT 
                        time_bucket($4, timestamp) AS bucket,
                        symbol,
                        exchange,
                        first(price, timestamp) AS open_price,
                        last(price, timestamp) AS close_price,
                        max(high) AS high_price,
                        min(low) AS low_price,
                        sum(volume) AS total_volume,
                        avg(price) AS avg_price
                    FROM market_data_ts 
                    WHERE symbol = $1 
                    AND exchange = $2 
                    AND timestamp >= $3 
                    AND timestamp <= $5
                    GROUP BY bucket, symbol, exchange
                    ORDER BY bucket;
                """
                
                # Convert interval to PostgreSQL interval
                interval_mapping = {
                    '1m': '1 minute',
                    '5m': '5 minutes', 
                    '15m': '15 minutes',
                    '1h': '1 hour',
                    '4h': '4 hours',
                    '1d': '1 day'
                }
                
                pg_interval = interval_mapping.get(interval, '1 minute')
                
                rows = await conn.fetch(query, symbol, exchange, start_time, pg_interval, end_time)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Error in optimized market data query: {str(e)}")
            return []
    
    async def get_user_portfolio_performance(self, user_id: str, 
                                           days: int = 30) -> Dict[str, Any]:
        """Get user portfolio performance using materialized view"""
        
        try:
            async with self.connection_manager.get_db_connection() as conn:
                query = """
                    SELECT 
                        day,
                        end_value,
                        start_value,
                        final_pnl_percent,
                        (end_value - start_value) AS daily_pnl,
                        max_value,
                        min_value
                    FROM daily_portfolio_performance 
                    WHERE user_id = $1 
                    AND day >= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY day DESC;
                """ % days
                
                rows = await conn.fetch(query, user_id)
                
                if not rows:
                    return {'performance': [], 'summary': {}}
                
                # Calculate summary statistics
                total_pnl = sum(row['daily_pnl'] for row in rows if row['daily_pnl'])
                avg_daily_return = sum(row['final_pnl_percent'] for row in rows) / len(rows)
                
                return {
                    'performance': [dict(row) for row in rows],
                    'summary': {
                        'total_pnl': total_pnl,
                        'avg_daily_return_percent': avg_daily_return,
                        'best_day_pnl': max(row['daily_pnl'] for row in rows if row['daily_pnl']),
                        'worst_day_pnl': min(row['daily_pnl'] for row in rows if row['daily_pnl']),
                        'days_tracked': len(rows)
                    }
                }
                
        except Exception as e:
            logger.error(f"Error in portfolio performance query: {str(e)}")
            return {'performance': [], 'summary': {}}
    
    async def get_top_performing_signals(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get top performing signals using materialized view"""
        
        try:
            async with self.connection_manager.get_db_connection() as conn:
                query = """
                    SELECT * FROM top_performing_signals 
                    WHERE day >= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY avg_confidence DESC, avg_strength DESC
                    LIMIT 50;
                """ % days
                
                rows = await conn.fetch(query)
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Error in top signals query: {str(e)}")
            return []

# Example usage
async def main():
    """Example usage of TimescaleDB migration"""
    from core.performance_optimizer import performance_optimizer
    
    # Initialize performance optimizer
    await performance_optimizer.initialize()
    
    # Create migration instance
    migration = TimescaleDBMigration(performance_optimizer.connection_manager)
    
    # Run migration
    result = await migration.run_full_migration()
    
    if result['success']:
        print("✅ TimescaleDB migration completed successfully!")
        print(f"📊 Migration stats: {json.dumps(result['stats'], indent=2)}")
        print(f"⏱️  Migration duration: {result['migration_duration']:.2f} seconds")
        
        # Test query optimizer
        query_optimizer = TimescaleQueryOptimizer(performance_optimizer.connection_manager)
        
        # Example queries
        end_time = datetime.now()
        start_time = end_time - timedelta(days=1)
        
        # Test market data query
        market_data = await query_optimizer.get_market_data_optimized(
            "BTC/USDT", "binance", start_time, end_time, "1h"
        )
        print(f"📈 Retrieved {len(market_data)} market data points")
        
    else:
        print(f"❌ TimescaleDB migration failed: {result.get('error')}")
    
    # Cleanup
    await performance_optimizer.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
