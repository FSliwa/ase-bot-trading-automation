"""
Advanced Performance Optimizer for ASE Trading Bot
Optimized for 16GB RAM, 6 cores @ 2.271GHz server
"""

import asyncio
import uvloop
import concurrent.futures
import psutil
import gc
import os
import sys
from typing import Dict, List, Optional, Any, Callable
import logging
from functools import lru_cache, wraps
import time
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass
import asyncpg
import aioredis
import json
from datetime import datetime, timedelta

# Set uvloop as default event loop for better performance
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

logger = logging.getLogger(__name__)

@dataclass
class SystemResources:
    """System resource configuration for optimization"""
    total_ram_gb: float = 16.0
    cpu_cores: int = 6
    cpu_frequency_ghz: float = 2.271
    max_ram_usage_percent: float = 75.0  # Use max 12GB of 16GB
    max_cpu_usage_percent: float = 80.0
    
    @property
    def max_ram_bytes(self) -> int:
        return int(self.total_ram_gb * 1024**3 * self.max_ram_usage_percent / 100)
    
    @property
    def optimal_workers(self) -> int:
        """Calculate optimal worker count based on CPU cores"""
        return min(self.cpu_cores - 1, 4)  # Leave 1-2 cores for system
    
    @property
    def db_connections(self) -> int:
        """Optimal database connection pool size"""
        return min(20, self.cpu_cores * 3)
    
    @property
    def redis_connections(self) -> int:
        """Optimal Redis connection pool size"""
        return min(15, self.cpu_cores * 2)

class ResourceMonitor:
    """Monitor system resources and trigger optimization actions"""
    
    def __init__(self, resources: SystemResources):
        self.resources = resources
        self.monitoring = False
        self.alerts: List[Dict] = []
        
    async def start_monitoring(self):
        """Start continuous resource monitoring"""
        self.monitoring = True
        
        while self.monitoring:
            await self.check_resources()
            await asyncio.sleep(30)  # Check every 30 seconds
    
    async def check_resources(self):
        """Check current resource usage and trigger alerts"""
        # Memory check
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        if memory_percent > self.resources.max_ram_usage_percent:
            alert = {
                'type': 'high_memory',
                'value': memory_percent,
                'threshold': self.resources.max_ram_usage_percent,
                'timestamp': datetime.now(),
                'action': 'garbage_collection_triggered'
            }
            self.alerts.append(alert)
            logger.warning(f"High memory usage: {memory_percent}%")
            
            # Trigger garbage collection
            gc.collect()
            
        # CPU check
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > self.resources.max_cpu_usage_percent:
            alert = {
                'type': 'high_cpu',
                'value': cpu_percent,
                'threshold': self.resources.max_cpu_usage_percent,
                'timestamp': datetime.now(),
                'action': 'request_throttling'
            }
            self.alerts.append(alert)
            logger.warning(f"High CPU usage: {cpu_percent}%")
    
    def get_current_usage(self) -> Dict[str, float]:
        """Get current resource usage statistics"""
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        
        return {
            'memory_percent': memory.percent,
            'memory_used_gb': memory.used / (1024**3),
            'memory_available_gb': memory.available / (1024**3),
            'cpu_percent': cpu_percent,
            'cpu_cores': psutil.cpu_count(),
            'cpu_frequency': psutil.cpu_freq().current / 1000 if psutil.cpu_freq() else 0.0,
            'disk_usage_percent': psutil.disk_usage('/').percent
        }

class OptimizedConnectionManager:
    """Optimized connection manager for database and Redis"""
    
    def __init__(self, resources: SystemResources):
        self.resources = resources
        self.pg_pool: Optional[asyncpg.Pool] = None
        self.redis_pool: Optional[aioredis.ConnectionPool] = None
        self.connection_stats = {
            'pg_active': 0,
            'pg_idle': 0,
            'redis_active': 0,
            'redis_idle': 0
        }
        
    async def initialize(self):
        """Initialize optimized connection pools"""
        
        # PostgreSQL connection pool with optimized settings
        self.pg_pool = await asyncpg.create_pool(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'trading_user'),
            password=os.getenv('POSTGRES_PASSWORD'),
            database=os.getenv('POSTGRES_DB', 'trading_bot'),
            min_size=5,
            max_size=self.resources.db_connections,
            max_queries=50000,
            max_inactive_connection_lifetime=300.0,
            command_timeout=60.0,
            server_settings={
                'application_name': 'ase_trading_bot',
                'tcp_keepalives_idle': '600',
                'tcp_keepalives_interval': '30',
                'tcp_keepalives_count': '3',
                'shared_preload_libraries': 'pg_stat_statements,timescaledb'
            }
        )
        
        # Redis connection pool with optimized settings
        self.redis_pool = aioredis.ConnectionPool(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            password=os.getenv('REDIS_PASSWORD'),
            db=0,
            max_connections=self.resources.redis_connections,
            retry_on_timeout=True,
            health_check_interval=30,
            encoding='utf-8',
            decode_responses=True
        )
        
        logger.info(f"Initialized connection pools: PG({self.resources.db_connections}), Redis({self.resources.redis_connections})")
    
    @asynccontextmanager
    async def get_db_connection(self):
        """Get database connection with proper resource tracking"""
        if not self.pg_pool:
            raise RuntimeError("Connection pool not initialized")
            
        async with self.pg_pool.acquire() as conn:
            self.connection_stats['pg_active'] += 1
            try:
                yield conn
            finally:
                self.connection_stats['pg_active'] -= 1
                self.connection_stats['pg_idle'] = self.pg_pool.get_size() - self.connection_stats['pg_active']
    
    @asynccontextmanager
    async def get_redis_connection(self):
        """Get Redis connection with proper resource tracking"""
        if not self.redis_pool:
            raise RuntimeError("Redis pool not initialized")
            
        redis = aioredis.Redis(connection_pool=self.redis_pool)
        self.connection_stats['redis_active'] += 1
        try:
            yield redis
        finally:
            await redis.close()
            self.connection_stats['redis_active'] -= 1
    
    async def execute_batch_db(self, queries: List[tuple]) -> List[Any]:
        """Execute multiple database queries in batch for better performance"""
        results = []
        
        async with self.get_db_connection() as conn:
            # Use transaction for batch operations
            async with conn.transaction():
                for query, *params in queries:
                    if params:
                        result = await conn.fetch(query, *params[0])
                    else:
                        result = await conn.fetch(query)
                    results.append(result)
        
        return results
    
    async def execute_redis_pipeline(self, commands: List[tuple]) -> List[Any]:
        """Execute Redis commands in pipeline for better performance"""
        async with self.get_redis_connection() as redis:
            pipe = redis.pipeline()
            
            for command, *args in commands:
                getattr(pipe, command)(*args)
            
            results = await pipe.execute()
            return results
    
    async def close(self):
        """Properly close all connections"""
        if self.pg_pool:
            await self.pg_pool.close()
            
        if self.redis_pool:
            await self.redis_pool.disconnect()

class AdvancedCacheManager:
    """Advanced caching system with LRU and TTL support"""
    
    def __init__(self, connection_manager: OptimizedConnectionManager, max_memory_mb: int = 512):
        self.connection_manager = connection_manager
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.current_memory = 0
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'memory_usage_mb': 0
        }
        
        # LRU cache for frequently accessed data
        self.memory_cache = {}
        self.access_order = []
        
    def cache_decorator(self, ttl: int = 300, key_prefix: str = ""):
        """Decorator for caching function results"""
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Generate cache key
                cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"
                
                # Check memory cache first
                if cache_key in self.memory_cache:
                    cached_data, expires_at = self.memory_cache[cache_key]
                    if datetime.now() < expires_at:
                        self.cache_stats['hits'] += 1
                        self._update_access_order(cache_key)
                        return cached_data
                    else:
                        # Expired, remove from cache
                        del self.memory_cache[cache_key]
                        self.access_order.remove(cache_key)
                
                # Check Redis cache
                async with self.connection_manager.get_redis_connection() as redis:
                    cached_value = await redis.get(cache_key)
                    
                    if cached_value:
                        self.cache_stats['hits'] += 1
                        try:
                            result = json.loads(cached_value)
                            # Also store in memory cache
                            await self._store_in_memory(cache_key, result, ttl)
                            return result
                        except json.JSONDecodeError:
                            pass
                
                # Cache miss, execute function
                self.cache_stats['misses'] += 1
                result = await func(*args, **kwargs)
                
                # Store in both Redis and memory cache
                await self._store_in_caches(cache_key, result, ttl)
                
                return result
            return wrapper
        return decorator
    
    async def _store_in_caches(self, key: str, data: Any, ttl: int):
        """Store data in both memory and Redis cache"""
        # Store in Redis
        async with self.connection_manager.get_redis_connection() as redis:
            serialized_data = json.dumps(data, default=str)
            await redis.setex(key, ttl, serialized_data)
        
        # Store in memory cache
        await self._store_in_memory(key, data, ttl)
    
    async def _store_in_memory(self, key: str, data: Any, ttl: int):
        """Store data in memory cache with LRU eviction"""
        expires_at = datetime.now() + timedelta(seconds=ttl)
        data_size = sys.getsizeof(data)
        
        # Check if we need to evict items
        while self.current_memory + data_size > self.max_memory_bytes and self.access_order:
            oldest_key = self.access_order.pop(0)
            if oldest_key in self.memory_cache:
                old_data, _ = self.memory_cache[oldest_key]
                self.current_memory -= sys.getsizeof(old_data)
                del self.memory_cache[oldest_key]
                self.cache_stats['evictions'] += 1
        
        # Store new data
        self.memory_cache[key] = (data, expires_at)
        self.access_order.append(key)
        self.current_memory += data_size
        self.cache_stats['memory_usage_mb'] = self.current_memory / (1024 * 1024)
    
    def _update_access_order(self, key: str):
        """Update access order for LRU"""
        if key in self.access_order:
            self.access_order.remove(key)
            self.access_order.append(key)
    
    async def invalidate(self, pattern: str):
        """Invalidate cache entries matching pattern"""
        # Invalidate memory cache
        keys_to_remove = [k for k in self.memory_cache.keys() if pattern in k]
        for key in keys_to_remove:
            if key in self.memory_cache:
                old_data, _ = self.memory_cache[key]
                self.current_memory -= sys.getsizeof(old_data)
                del self.memory_cache[key]
                self.access_order.remove(key)
        
        # Invalidate Redis cache
        async with self.connection_manager.get_redis_connection() as redis:
            keys = await redis.keys(f"*{pattern}*")
            if keys:
                await redis.delete(*keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.cache_stats['hits'] + self.cache_stats['misses']
        hit_rate = (self.cache_stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            **self.cache_stats,
            'hit_rate_percent': round(hit_rate, 2),
            'memory_entries': len(self.memory_cache),
            'total_requests': total_requests
        }

class BatchDataProcessor:
    """Optimized batch data processor for market data"""
    
    def __init__(self, connection_manager: OptimizedConnectionManager, 
                 cache_manager: AdvancedCacheManager):
        self.connection_manager = connection_manager
        self.cache_manager = cache_manager
        self.processing_stats = {
            'batches_processed': 0,
            'total_items': 0,
            'avg_batch_time': 0.0,
            'errors': 0
        }
        
    async def process_market_data_batch(self, market_data_batch: List[Dict]) -> Dict[str, Any]:
        """Process batch of market data with optimizations"""
        start_time = time.time()
        
        try:
            # Group data by symbol for efficient processing
            symbol_groups = {}
            for data in market_data_batch:
                symbol = data.get('symbol', 'UNKNOWN')
                if symbol not in symbol_groups:
                    symbol_groups[symbol] = []
                symbol_groups[symbol].append(data)
            
            # Process each symbol group
            results = {}
            tasks = []
            
            # Limit concurrent symbol processing
            semaphore = asyncio.Semaphore(4)  # Max 4 symbols processed simultaneously
            
            async def process_symbol_group(symbol: str, data_list: List[Dict]):
                async with semaphore:
                    return await self._process_symbol_data(symbol, data_list)
            
            # Create tasks for all symbol groups
            for symbol, data_list in symbol_groups.items():
                task = process_symbol_group(symbol, data_list)
                tasks.append((symbol, task))
            
            # Execute all tasks
            for symbol, task in tasks:
                try:
                    result = await task
                    results[symbol] = result
                except Exception as e:
                    logger.error(f"Error processing {symbol}: {str(e)}")
                    self.processing_stats['errors'] += 1
                    results[symbol] = {'error': str(e)}
            
            # Update statistics
            processing_time = time.time() - start_time
            self.processing_stats['batches_processed'] += 1
            self.processing_stats['total_items'] += len(market_data_batch)
            self.processing_stats['avg_batch_time'] = (
                (self.processing_stats['avg_batch_time'] * (self.processing_stats['batches_processed'] - 1) + processing_time) /
                self.processing_stats['batches_processed']
            )
            
            return {
                'success': True,
                'results': results,
                'processing_time': processing_time,
                'items_processed': len(market_data_batch),
                'symbols_processed': len(symbol_groups)
            }
            
        except Exception as e:
            self.processing_stats['errors'] += 1
            logger.error(f"Batch processing error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'processing_time': time.time() - start_time
            }
    
    @lru_cache(maxsize=1000)
    async def _process_symbol_data(self, symbol: str, data_list: List[Dict]) -> Dict[str, Any]:
        """Process data for a specific symbol with caching"""
        
        # Sort data by timestamp for time-series processing
        sorted_data = sorted(data_list, key=lambda x: x.get('timestamp', 0))
        
        # Calculate technical indicators
        indicators = await self._calculate_indicators(symbol, sorted_data)
        
        # Store processed data in database (batch insert)
        await self._store_symbol_data(symbol, sorted_data)
        
        # Cache results
        cache_key = f"symbol_data:{symbol}:{len(sorted_data)}"
        await self.cache_manager._store_in_caches(
            cache_key, 
            {'indicators': indicators, 'data_points': len(sorted_data)}, 
            300  # 5 minute TTL
        )
        
        return {
            'symbol': symbol,
            'data_points': len(sorted_data),
            'indicators': indicators,
            'latest_price': sorted_data[-1].get('price', 0) if sorted_data else 0
        }
    
    async def _calculate_indicators(self, symbol: str, data: List[Dict]) -> Dict[str, float]:
        """Calculate technical indicators for symbol data"""
        if not data or len(data) < 2:
            return {}
        
        prices = [float(d.get('price', 0)) for d in data]
        volumes = [float(d.get('volume', 0)) for d in data]
        
        # Basic indicators
        indicators = {
            'current_price': prices[-1],
            'price_change': prices[-1] - prices[0] if len(prices) > 1 else 0,
            'price_change_percent': ((prices[-1] - prices[0]) / prices[0] * 100) if prices[0] > 0 else 0,
            'avg_price': sum(prices) / len(prices),
            'max_price': max(prices),
            'min_price': min(prices),
            'total_volume': sum(volumes),
            'avg_volume': sum(volumes) / len(volumes) if volumes else 0
        }
        
        # Simple Moving Average (if enough data)
        if len(prices) >= 20:
            indicators['sma_20'] = sum(prices[-20:]) / 20
        
        if len(prices) >= 50:
            indicators['sma_50'] = sum(prices[-50:]) / 50
        
        # Volatility (standard deviation)
        if len(prices) >= 10:
            avg_price = indicators['avg_price']
            variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
            indicators['volatility'] = variance ** 0.5
        
        return indicators
    
    async def _store_symbol_data(self, symbol: str, data_list: List[Dict]):
        """Store symbol data in database using batch insert"""
        
        if not data_list:
            return
        
        # Prepare batch insert query
        insert_query = """
            INSERT INTO market_data (symbol, timestamp, price, volume, high, low, open, close)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (symbol, timestamp) DO UPDATE SET
                price = EXCLUDED.price,
                volume = EXCLUDED.volume,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                open = EXCLUDED.open,
                close = EXCLUDED.close
        """
        
        # Prepare data for batch insert
        insert_data = []
        for data in data_list:
            insert_data.append((
                symbol,
                datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())),
                float(data.get('price', 0)),
                float(data.get('volume', 0)),
                float(data.get('high', data.get('price', 0))),
                float(data.get('low', data.get('price', 0))),
                float(data.get('open', data.get('price', 0))),
                float(data.get('close', data.get('price', 0)))
            ))
        
        # Execute batch insert
        async with self.connection_manager.get_db_connection() as conn:
            await conn.executemany(insert_query, insert_data)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return {
            **self.processing_stats,
            'avg_items_per_batch': (
                self.processing_stats['total_items'] / self.processing_stats['batches_processed']
                if self.processing_stats['batches_processed'] > 0 else 0
            )
        }

class PerformanceOptimizer:
    """Main performance optimizer orchestrating all components"""
    
    def __init__(self):
        self.resources = SystemResources()
        self.monitor = ResourceMonitor(self.resources)
        self.connection_manager = OptimizedConnectionManager(self.resources)
        self.cache_manager = AdvancedCacheManager(self.connection_manager)
        self.batch_processor = BatchDataProcessor(self.connection_manager, self.cache_manager)
        
        # Process and thread pools for CPU-intensive tasks
        self.process_pool = concurrent.futures.ProcessPoolExecutor(
            max_workers=self.resources.optimal_workers
        )
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=min(20, self.resources.cpu_cores * 3)
        )
        
        self.initialized = False
        self.optimization_stats = {
            'start_time': None,
            'requests_processed': 0,
            'avg_response_time': 0.0,
            'memory_optimizations': 0,
            'cache_optimizations': 0
        }
    
    async def initialize(self):
        """Initialize all optimization components"""
        logger.info("Initializing Performance Optimizer...")
        
        # Initialize connection manager
        await self.connection_manager.initialize()
        
        # Start resource monitoring
        asyncio.create_task(self.monitor.start_monitoring())
        
        # Set optimization start time
        self.optimization_stats['start_time'] = datetime.now()
        
        self.initialized = True
        logger.info("Performance Optimizer initialized successfully")
    
    async def optimize_request(self, request_func: Callable, *args, **kwargs) -> Any:
        """Optimize any request with performance monitoring"""
        if not self.initialized:
            raise RuntimeError("Performance optimizer not initialized")
        
        start_time = time.time()
        
        try:
            # Execute request
            result = await request_func(*args, **kwargs)
            
            # Update statistics
            processing_time = time.time() - start_time
            self.optimization_stats['requests_processed'] += 1
            self.optimization_stats['avg_response_time'] = (
                (self.optimization_stats['avg_response_time'] * (self.optimization_stats['requests_processed'] - 1) + processing_time) /
                self.optimization_stats['requests_processed']
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Request optimization error: {str(e)}")
            raise
        finally:
            # Trigger garbage collection if needed
            await self._check_memory_optimization()
    
    async def _check_memory_optimization(self):
        """Check if memory optimization is needed"""
        memory_usage = psutil.virtual_memory().percent
        
        if memory_usage > 70:  # If memory usage > 70%
            gc.collect()
            self.optimization_stats['memory_optimizations'] += 1
            logger.info(f"Memory optimization triggered at {memory_usage}% usage")
    
    async def process_market_data_optimized(self, market_data: List[Dict]) -> Dict[str, Any]:
        """Process market data with full optimization pipeline"""
        
        # Use batch processor for efficient processing
        result = await self.batch_processor.process_market_data_batch(market_data)
        
        return result
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        
        current_usage = self.monitor.get_current_usage()
        cache_stats = self.cache_manager.get_stats()
        processing_stats = self.batch_processor.get_stats()
        
        uptime = (datetime.now() - self.optimization_stats['start_time']).total_seconds() if self.optimization_stats['start_time'] else 0
        
        return {
            'system_resources': {
                'configured': {
                    'total_ram_gb': self.resources.total_ram_gb,
                    'cpu_cores': self.resources.cpu_cores,
                    'cpu_frequency_ghz': self.resources.cpu_frequency_ghz
                },
                'current_usage': current_usage,
                'resource_alerts': len(self.monitor.alerts)
            },
            'connection_pools': {
                'postgres': {
                    'max_size': self.resources.db_connections,
                    'current_stats': self.connection_manager.connection_stats
                },
                'redis': {
                    'max_size': self.resources.redis_connections
                }
            },
            'cache_performance': cache_stats,
            'batch_processing': processing_stats,
            'optimization_stats': {
                **self.optimization_stats,
                'uptime_seconds': uptime,
                'requests_per_second': (
                    self.optimization_stats['requests_processed'] / uptime
                    if uptime > 0 else 0
                )
            }
        }
    
    async def cleanup(self):
        """Cleanup all resources"""
        logger.info("Cleaning up Performance Optimizer...")
        
        # Stop monitoring
        self.monitor.monitoring = False
        
        # Close connection pools
        await self.connection_manager.close()
        
        # Shutdown process and thread pools
        self.process_pool.shutdown(wait=True)
        self.thread_pool.shutdown(wait=True)
        
        # Force garbage collection
        gc.collect()
        
        logger.info("Performance Optimizer cleanup completed")

# Global optimizer instance
performance_optimizer = PerformanceOptimizer()

# Convenience functions for FastAPI integration
async def optimize_api_request(request_func: Callable, *args, **kwargs):
    """Optimize any API request"""
    return await performance_optimizer.optimize_request(request_func, *args, **kwargs)

async def get_system_performance_stats():
    """Get current system performance statistics"""
    return performance_optimizer.get_performance_report()

# Example usage
if __name__ == "__main__":
    async def main():
        # Initialize optimizer
        await performance_optimizer.initialize()
        
        # Test market data processing
        test_market_data = [
            {
                'symbol': 'BTC/USDT',
                'timestamp': datetime.now().isoformat(),
                'price': 45000.0,
                'volume': 1000000.0
            },
            {
                'symbol': 'ETH/USDT',
                'timestamp': datetime.now().isoformat(),
                'price': 3000.0,
                'volume': 500000.0
            }
        ]
        
        # Process with optimization
        result = await performance_optimizer.process_market_data_optimized(test_market_data)
        print("Processing result:", result)
        
        # Get performance report
        report = performance_optimizer.get_performance_report()
        print("Performance report:", json.dumps(report, indent=2, default=str))
        
        # Cleanup
        await performance_optimizer.cleanup()
    
    # Run example
    asyncio.run(main())
