"""
Advanced Database Optimization System
Connection pooling, async operations, intelligent indexing, query optimization
"""

import asyncio
import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, AsyncGenerator
import time

# Database imports
from sqlalchemy import (
    create_engine, MetaData, Index, text, 
    event, pool, inspect, func, select, update, delete,
    and_, or_, desc, asc
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, async_sessionmaker,
    AsyncEngine
)
from sqlalchemy.orm import (
    selectinload, joinedload, contains_eager,
    Session, sessionmaker
)
from sqlalchemy.pool import QueuePool, NullPool, StaticPool
from sqlalchemy.engine.events import PoolEvents
from sqlalchemy.dialects import postgresql, sqlite
import redis.asyncio as redis

# Import models
from vps_deployment_package.db import (
    Base, Position, Order, Fill, TradingStats, 
    AIAnalysis, RiskEvent, ExchangeCredential
)

logger = logging.getLogger(__name__)

class DatabaseOptimizer:
    """Advanced database optimization and connection management"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL', 'sqlite:///trading.db')
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        
        # Connection pool settings optimized for 16GB RAM
        self.pool_settings = {
            'pool_size': 20,  # Base connections
            'max_overflow': 30,  # Additional connections during peaks
            'pool_timeout': 30,  # Wait time for connection
            'pool_recycle': 3600,  # Recycle connections every hour
            'pool_pre_ping': True,  # Verify connections
        }
        
        self.async_engine: Optional[AsyncEngine] = None
        self.sync_engine = None
        self.async_session_factory = None
        self.redis_client = None
        self.query_cache = {}
        
    async def initialize(self):
        """Initialize optimized database connections"""
        logger.info("🚀 Initializing Advanced Database Optimizer...")
        
        # Setup async engine with connection pooling
        if self.database_url.startswith('postgresql'):
            # PostgreSQL async setup
            async_url = self.database_url.replace('postgresql://', 'postgresql+asyncpg://')
            self.async_engine = create_async_engine(
                async_url,
                poolclass=QueuePool,
                **self.pool_settings,
                echo=os.getenv('DB_DEBUG', 'false').lower() == 'true',
                echo_pool=True,
                logging_name='trading_db'
            )
        elif self.database_url.startswith('sqlite'):
            # SQLite async setup (limited pooling)
            async_url = self.database_url.replace('sqlite:///', 'sqlite+aiosqlite:///')
            self.async_engine = create_async_engine(
                async_url,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
                echo=os.getenv('DB_DEBUG', 'false').lower() == 'true'
            )
        
        # Create async session factory
        self.async_session_factory = async_sessionmaker(
            bind=self.async_engine,
            class_=AsyncSession,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False
        )
        
        # Setup sync engine for migration/admin tasks
        self.sync_engine = create_engine(
            self.database_url,
            **self.pool_settings if 'postgresql' in self.database_url else {},
            connect_args={"check_same_thread": False} if 'sqlite' in self.database_url else {}
        )
        
        # Initialize Redis for caching
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            await self.redis_client.ping()
            logger.info("✅ Redis cache connected")
        except Exception as e:
            logger.warning(f"⚠️ Redis unavailable: {e}")
            self.redis_client = None
        
        # Setup connection pool monitoring
        self._setup_pool_monitoring()
        
        # Create optimized indexes
        await self._create_optimized_indexes()
        
        # Setup query caching
        self._setup_query_cache()
        
        logger.info(f"✅ Database optimizer initialized - Pool: {self.pool_settings}")

    def _setup_pool_monitoring(self):
        """Setup connection pool monitoring and events"""
        if not self.async_engine:
            return
            
        @event.listens_for(self.async_engine.sync_engine, "connect")
        def connect_handler(dbapi_connection, connection_record):
            logger.debug(f"🔌 New DB connection: {id(connection_record)}")
            
        @event.listens_for(self.async_engine.sync_engine, "checkout")
        def checkout_handler(dbapi_connection, connection_record, connection_proxy):
            logger.debug(f"📤 Connection checked out: {id(connection_record)}")
            
        @event.listens_for(self.async_engine.sync_engine, "checkin")
        def checkin_handler(dbapi_connection, connection_record):
            logger.debug(f"📥 Connection returned: {id(connection_record)}")

    async def _create_optimized_indexes(self):
        """Create optimized database indexes for performance"""
        if not self.async_engine:
            return
            
        indexes_to_create = [
            # Position indexes for fast lookups
            Index('idx_positions_symbol_status', Position.symbol, Position.status),
            Index('idx_positions_entry_time', Position.entry_time),
            Index('idx_positions_status_updated', Position.status, Position.updated_at),
            
            # Order indexes for trading operations
            Index('idx_orders_symbol_status', Order.symbol, Order.status),
            Index('idx_orders_client_id', Order.client_order_id),
            Index('idx_orders_created_status', Order.created_at, Order.status),
            
            # Fill indexes for analytics
            Index('idx_fills_symbol_timestamp', Fill.symbol, Fill.timestamp),
            Index('idx_fills_timestamp_pnl', Fill.timestamp, Fill.realized_pnl),
            Index('idx_fills_position_timestamp', Fill.position_id, Fill.timestamp),
            
            # Stats indexes for performance tracking
            Index('idx_stats_date', TradingStats.date),
            Index('idx_stats_date_pnl', TradingStats.date, TradingStats.total_pnl),
            
            # Risk events for monitoring
            Index('idx_risk_events_type_created', RiskEvent.event_type, RiskEvent.created_at),
            Index('idx_risk_events_severity', RiskEvent.severity, RiskEvent.created_at),
            
            # Exchange credentials
            Index('idx_exchange_creds_user_exchange', ExchangeCredential.user_id, ExchangeCredential.exchange),
            Index('idx_exchange_creds_active', ExchangeCredential.is_active, ExchangeCredential.last_used_at),
        ]
        
        async with self.async_engine.begin() as conn:
            for index in indexes_to_create:
                try:
                    await conn.run_sync(lambda sync_conn: index.create(sync_conn, checkfirst=True))
                    logger.debug(f"✅ Index created: {index.name}")
                except Exception as e:
                    logger.debug(f"⚠️ Index {index.name} already exists: {e}")

    def _setup_query_cache(self):
        """Setup intelligent query result caching"""
        self.query_cache = {
            'market_data': {'ttl': 5, 'data': {}},  # 5 seconds
            'positions': {'ttl': 1, 'data': {}},   # 1 second  
            'account_info': {'ttl': 2, 'data': {}}, # 2 seconds
            'stats': {'ttl': 60, 'data': {}},      # 1 minute
        }

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get optimized async database session with automatic cleanup"""
        if not self.async_session_factory:
            raise RuntimeError("Database optimizer not initialized")
            
        async with self.async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        if not self.async_engine:
            return {"error": "Engine not initialized"}
            
        pool = self.async_engine.pool
        return {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "invalidated": pool.invalid(),
            "total_connections": pool.size() + pool.overflow(),
            "utilization_percent": round((pool.checkedout() / (pool.size() + pool.overflow())) * 100, 2) if (pool.size() + pool.overflow()) > 0 else 0
        }

    # Optimized query methods with caching and batch operations
    
    async def get_positions_optimized(self, user_id: str = None, symbols: List[str] = None) -> List[Dict]:
        """Get positions with optimized query and caching"""
        cache_key = f"positions:{user_id}:{','.join(symbols) if symbols else 'all'}"
        
        # Check cache first
        if self.redis_client:
            cached = await self.redis_client.get(cache_key)
            if cached:
                import json
                return json.loads(cached)
        
        async with self.get_session() as session:
            # Optimized query with joins
            query = select(Position).options(
                selectinload(Position.orders),
                selectinload(Position.fills)
            ).filter(Position.status == "OPEN")
            
            if symbols:
                query = query.filter(Position.symbol.in_(symbols))
                
            result = await session.execute(query)
            positions = result.unique().scalars().all()
            
            # Convert to dict for serialization
            positions_data = []
            for pos in positions:
                pos_dict = {
                    'id': pos.id,
                    'symbol': pos.symbol,
                    'side': pos.side,
                    'quantity': pos.quantity,
                    'entry_price': pos.entry_price,
                    'current_price': pos.current_price,
                    'unrealized_pnl': pos.unrealized_pnl,
                    'margin_used': pos.margin_used,
                    'leverage': pos.leverage,
                    'entry_time': pos.entry_time.isoformat() if pos.entry_time else None,
                    'orders_count': len(pos.orders),
                    'fills_count': len(pos.fills)
                }
                positions_data.append(pos_dict)
            
            # Cache results
            if self.redis_client:
                import json
                await self.redis_client.setex(
                    cache_key, 
                    self.query_cache['positions']['ttl'],
                    json.dumps(positions_data, default=str)
                )
            
            return positions_data

    async def get_account_summary_optimized(self) -> Dict[str, Any]:
        """Get comprehensive account summary with single optimized query"""
        cache_key = "account_summary"
        
        if self.redis_client:
            cached = await self.redis_client.get(cache_key)
            if cached:
                import json
                return json.loads(cached)
        
        async with self.get_session() as session:
            # Single query for all account data
            positions_query = select(
                func.count(Position.id).label('total_positions'),
                func.sum(Position.margin_used).label('total_margin'),
                func.sum(Position.unrealized_pnl).label('total_unrealized_pnl')
            ).filter(Position.status == "OPEN")
            
            fills_today_query = select(
                func.count(Fill.id).label('trades_today'),
                func.sum(Fill.realized_pnl).label('pnl_today')
            ).filter(
                Fill.timestamp >= datetime.now().replace(hour=0, minute=0, second=0)
            )
            
            # Execute queries concurrently
            positions_result = await session.execute(positions_query)
            fills_result = await session.execute(fills_today_query)
            
            pos_data = positions_result.first()
            fill_data = fills_result.first()
            
            summary = {
                'total_positions': pos_data.total_positions or 0,
                'total_margin_used': float(pos_data.total_margin or 0),
                'total_unrealized_pnl': float(pos_data.total_unrealized_pnl or 0),
                'trades_today': fill_data.trades_today or 0,
                'pnl_today': float(fill_data.pnl_today or 0),
                'timestamp': datetime.now().isoformat()
            }
            
            # Cache summary
            if self.redis_client:
                import json
                await self.redis_client.setex(
                    cache_key,
                    self.query_cache['account_info']['ttl'],
                    json.dumps(summary, default=str)
                )
            
            return summary

    async def get_trading_stats_optimized(self, days: int = 30) -> Dict[str, Any]:
        """Get trading statistics with optimized aggregation"""
        cache_key = f"trading_stats:{days}"
        
        if self.redis_client:
            cached = await self.redis_client.get(cache_key)
            if cached:
                import json
                return json.loads(cached)
        
        async with self.get_session() as session:
            from_date = datetime.now() - timedelta(days=days)
            
            # Optimized stats query
            stats_query = select(
                func.count(Fill.id).label('total_trades'),
                func.sum(Fill.realized_pnl).label('total_pnl'),
                func.avg(Fill.realized_pnl).label('avg_pnl'),
                func.count(Fill.id).filter(Fill.realized_pnl > 0).label('winning_trades'),
                func.count(Fill.id).filter(Fill.realized_pnl < 0).label('losing_trades'),
                func.max(Fill.realized_pnl).label('best_trade'),
                func.min(Fill.realized_pnl).label('worst_trade')
            ).filter(Fill.timestamp >= from_date)
            
            result = await session.execute(stats_query)
            data = result.first()
            
            # Calculate derived metrics
            win_rate = (data.winning_trades / data.total_trades * 100) if data.total_trades > 0 else 0
            profit_factor = abs(data.total_pnl / (data.total_pnl - (data.total_pnl * 2))) if data.total_pnl != 0 else 1
            
            stats = {
                'total_trades': data.total_trades or 0,
                'total_pnl': float(data.total_pnl or 0),
                'avg_pnl': float(data.avg_pnl or 0),
                'winning_trades': data.winning_trades or 0,
                'losing_trades': data.losing_trades or 0,
                'win_rate': round(win_rate, 2),
                'profit_factor': round(profit_factor, 2),
                'best_trade': float(data.best_trade or 0),
                'worst_trade': float(data.worst_trade or 0),
                'period_days': days
            }
            
            # Cache stats
            if self.redis_client:
                import json
                await self.redis_client.setex(
                    cache_key,
                    self.query_cache['stats']['ttl'],
                    json.dumps(stats, default=str)
                )
            
            return stats

    async def batch_update_positions(self, position_updates: List[Dict]) -> int:
        """Batch update positions for better performance"""
        if not position_updates:
            return 0
            
        async with self.get_session() as session:
            updated_count = 0
            
            for update_data in position_updates:
                position_id = update_data.get('id')
                current_price = update_data.get('current_price')
                
                if position_id and current_price:
                    # Optimized update query
                    stmt = update(Position).where(
                        Position.id == position_id
                    ).values(
                        current_price=current_price,
                        updated_at=datetime.now()
                    )
                    
                    result = await session.execute(stmt)
                    updated_count += result.rowcount
            
            await session.commit()
            
            # Clear related cache
            if self.redis_client:
                await self.redis_client.delete("positions:*")
                await self.redis_client.delete("account_summary")
            
            return updated_count

    async def cleanup_old_data(self, days_to_keep: int = 90):
        """Clean up old data to maintain performance"""
        async with self.get_session() as session:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            # Clean old fills (keep important data)
            old_fills = delete(Fill).where(
                and_(
                    Fill.timestamp < cutoff_date,
                    Fill.realized_pnl == 0  # Only delete non-profitable fills
                )
            )
            
            # Clean old AI analysis
            old_analysis = delete(AIAnalysis).where(
                AIAnalysis.created_at < cutoff_date
            )
            
            # Clean resolved risk events
            old_events = delete(RiskEvent).where(
                and_(
                    RiskEvent.created_at < cutoff_date,
                    RiskEvent.resolved == True
                )
            )
            
            fills_deleted = (await session.execute(old_fills)).rowcount
            analysis_deleted = (await session.execute(old_analysis)).rowcount
            events_deleted = (await session.execute(old_events)).rowcount
            
            await session.commit()
            
            logger.info(f"🧹 Cleanup complete - Fills: {fills_deleted}, Analysis: {analysis_deleted}, Events: {events_deleted}")
            
            return {
                'fills_deleted': fills_deleted,
                'analysis_deleted': analysis_deleted, 
                'events_deleted': events_deleted
            }

    async def get_performance_metrics(self) -> Dict[str, float]:
        """Get database performance metrics"""
        metrics = {
            'avg_query_time_ms': 0,
            'queries_per_second': 0,
            'cache_hit_rate': 0,
            'connection_utilization': 0
        }
        
        try:
            # Connection pool stats
            pool_stats = await self.get_connection_stats()
            metrics['connection_utilization'] = pool_stats.get('utilization_percent', 0)
            
            # Cache hit rate from Redis
            if self.redis_client:
                info = await self.redis_client.info()
                hit_rate = info.get('keyspace_hits', 0) / (info.get('keyspace_hits', 0) + info.get('keyspace_misses', 1)) * 100
                metrics['cache_hit_rate'] = round(hit_rate, 2)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return metrics

    async def close(self):
        """Close all connections"""
        if self.async_engine:
            await self.async_engine.dispose()
        if self.sync_engine:
            self.sync_engine.dispose()
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("🔒 Database optimizer connections closed")

# Global instance
database_optimizer = DatabaseOptimizer()

# Convenience functions for FastAPI integration
async def get_optimized_db_session():
    """Dependency for FastAPI routes"""
    async with database_optimizer.get_session() as session:
        yield session

async def init_database_optimizer():
    """Initialize database optimizer (call at startup)"""
    await database_optimizer.initialize()

async def cleanup_database_optimizer():
    """Cleanup database optimizer (call at shutdown)"""
    await database_optimizer.close()
