#!/usr/bin/env python3
"""
Analytics Engine Database Integration
Connects the advanced analytics engine with the new database tables
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from bot.db import DatabaseManager

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AnalyticsDBIntegrator:
    def __init__(self, db_manager_factory: Callable[[], DatabaseManager] = DatabaseManager):
        self.db_manager_factory = db_manager_factory
        self.cache_expiry_hours = {
            'sharpe_ratio': 1,
            'sortino_ratio': 1,
            'max_drawdown': 1,
            'var_95': 0.25,  # 15 minutes for risk metrics
            'cvar_95': 0.25,
            'portfolio_beta': 2,
            'portfolio_alpha': 2,
            'diversification_ratio': 6,
            'daily_returns': 0.1  # 6 minutes for returns
        }

    def _user_id(self, user_id: Any) -> str:
        return str(user_id)

    def _snapshot_user_ids(self) -> List[str]:
        with self.db_manager_factory() as db:
            return db.list_snapshot_user_ids()
    
    async def create_portfolio_snapshot(self, user_id: int, portfolio_data: Dict[str, Any]) -> int:
        """Create a new portfolio snapshot"""
        user_key = self._user_id(user_id)
        metadata = {
            'positions': portfolio_data.get('positions', {}),
            'metrics': portfolio_data.get('metrics', {}),
            'realized_pnl': portfolio_data.get('realized_pnl', 0.0),
            'day_change': portfolio_data.get('day_change', 0.0),
            'day_change_percent': portfolio_data.get('day_change_percent', 0.0),
            'positions_value': portfolio_data.get('positions_value', 0.0),
        }

        with self.db_manager_factory() as db:
            snapshot = db.record_portfolio_snapshot(
                user_id=user_key,
                total_balance=float(portfolio_data.get('total_value', 0.0)),
                available_balance=float(portfolio_data.get('cash_balance', portfolio_data.get('available_balance', 0.0))),
                margin_used=float(portfolio_data.get('margin_used', portfolio_data.get('positions_value', 0.0))),
                unrealized_pnl=float(portfolio_data.get('unrealized_pnl', 0.0)),
                metadata=metadata,
            )
            snapshot_id = snapshot.id

        logger.info(f"Created portfolio snapshot {snapshot_id} for user {user_key}")
        return snapshot_id
    
    async def get_portfolio_history(self, user_id: int, days: int = 30) -> List[Dict[str, Any]]:
        """Get portfolio history for calculations"""
        user_key = self._user_id(user_id)
        start_timestamp = datetime.utcnow() - timedelta(days=days)

        with self.db_manager_factory() as db:
            snapshots = db.get_portfolio_history(user_id=user_key, start_timestamp=start_timestamp)

        results: List[Dict[str, Any]] = []
        for snapshot in snapshots:
            metadata = snapshot.metadata_payload or {}
            results.append({
                'snapshot_date': snapshot.timestamp.isoformat(),
                'total_value': snapshot.total_balance,
                'cash_balance': snapshot.available_balance,
                'positions_value': metadata.get('positions_value', snapshot.margin_used),
                'unrealized_pnl': snapshot.unrealized_pnl,
                'realized_pnl': metadata.get('realized_pnl', 0.0),
                'day_change': metadata.get('day_change', 0.0),
                'day_change_percent': metadata.get('day_change_percent', 0.0),
                'positions': metadata.get('positions', {}),
                'metrics': metadata.get('metrics', {}),
            })

        return results
    
    async def cache_metric(self, user_id: int, metric_type: str, timeframe: str, 
                          value: float, metadata: Dict[str, Any] = None) -> bool:
        """Cache a calculated metric"""
        user_key = self._user_id(user_id)
        expires_at = datetime.utcnow() + timedelta(hours=self.cache_expiry_hours.get(metric_type, 1))

        with self.db_manager_factory() as db:
            db.upsert_metric_cache(
                user_id=user_key,
                metric_type=metric_type,
                timeframe=timeframe,
                value=float(value),
                metadata=metadata or {},
                expires_at=expires_at,
            )

        logger.debug(f"Cached metric {metric_type} for user {user_key}: {value}")
        return True
    
    async def get_cached_metric(self, user_id: int, metric_type: str, timeframe: str) -> Optional[Tuple[float, Dict[str, Any]]]:
        """Get cached metric if not expired"""
        user_key = self._user_id(user_id)
        with self.db_manager_factory() as db:
            record = db.get_latest_metric_cache(
                user_id=user_key,
                metric_type=metric_type,
                timeframe=timeframe,
            )

        if record:
            metadata = record.metadata_payload or {}
            logger.debug(f"Retrieved cached metric {metric_type} for user {user_key}: {record.value}")
            return record.value, metadata

        return None
    
    async def calculate_and_cache_sharpe_ratio(self, user_id: int, timeframe: str = "30d") -> float:
        """Calculate and cache Sharpe ratio"""
        # Check cache first
        cached = await self.get_cached_metric(user_id, 'sharpe_ratio', timeframe)
        if cached:
            return cached[0]
        
        # Get portfolio history
        days = int(timeframe.replace('d', '')) if 'd' in timeframe else 30
        history = await self.get_portfolio_history(user_id, days)
        
        if len(history) < 2:
            return 0.0
        
        # Calculate daily returns
        returns = []
        for i in range(1, len(history)):
            prev_value = history[i-1]['total_value']
            curr_value = history[i]['total_value']
            if prev_value > 0:
                daily_return = (curr_value - prev_value) / prev_value
                returns.append(daily_return)
        
        if not returns:
            return 0.0
        
        # Calculate Sharpe ratio (assuming risk-free rate of 0.02/365)
        risk_free_rate = 0.02 / 365
        excess_returns = [r - risk_free_rate for r in returns]
        
        if len(excess_returns) == 0 or np.std(excess_returns) == 0:
            sharpe_ratio = 0.0
        else:
            sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(365)
        
        # Cache the result
        await self.cache_metric(user_id, 'sharpe_ratio', timeframe, sharpe_ratio, {
            'calculation_date': datetime.now().isoformat(),
            'data_points': len(returns),
            'avg_return': np.mean(returns) if returns else 0,
            'volatility': np.std(returns) if returns else 0
        })
        
        return sharpe_ratio
    
    async def calculate_and_cache_max_drawdown(self, user_id: int, timeframe: str = "30d") -> float:
        """Calculate and cache maximum drawdown"""
        # Check cache first
        cached = await self.get_cached_metric(user_id, 'max_drawdown', timeframe)
        if cached:
            return cached[0]
        
        # Get portfolio history
        days = int(timeframe.replace('d', '')) if 'd' in timeframe else 30
        history = await self.get_portfolio_history(user_id, days)
        
        if len(history) < 2:
            return 0.0
        
        # Calculate maximum drawdown
        values = [h['total_value'] for h in history]
        peak = values[0]
        max_drawdown = 0.0
        
        for value in values[1:]:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak if peak > 0 else 0
            max_drawdown = max(max_drawdown, drawdown)
        
        # Cache the result
        await self.cache_metric(user_id, 'max_drawdown', timeframe, max_drawdown, {
            'calculation_date': datetime.now().isoformat(),
            'peak_value': peak,
            'data_points': len(values)
        })
        
        return max_drawdown
    
    async def calculate_and_cache_var(self, user_id: int, confidence: float = 0.95, timeframe: str = "30d") -> float:
        """Calculate and cache Value at Risk"""
        metric_type = f'var_{int(confidence * 100)}'
        
        # Check cache first
        cached = await self.get_cached_metric(user_id, metric_type, timeframe)
        if cached:
            return cached[0]
        
        # Get portfolio history
        days = int(timeframe.replace('d', '')) if 'd' in timeframe else 30
        history = await self.get_portfolio_history(user_id, days)
        
        if len(history) < 2:
            return 0.0
        
        # Calculate daily returns
        returns = []
        for i in range(1, len(history)):
            prev_value = history[i-1]['total_value']
            curr_value = history[i]['total_value']
            if prev_value > 0:
                daily_return = (curr_value - prev_value) / prev_value
                returns.append(daily_return)
        
        if not returns:
            return 0.0
        
        # Calculate VaR
        var = np.percentile(returns, (1 - confidence) * 100)
        current_value = history[-1]['total_value']
        var_amount = abs(var * current_value)
        
        # Cache the result
        await self.cache_metric(user_id, metric_type, timeframe, var_amount, {
            'calculation_date': datetime.now().isoformat(),
            'confidence_level': confidence,
            'current_value': current_value,
            'var_percentage': var,
            'data_points': len(returns)
        })
        
        return var_amount
    
    async def calculate_portfolio_metrics_batch(self, user_id: int, timeframe: str = "30d") -> Dict[str, float]:
        """Calculate all portfolio metrics in batch"""
        logger.info(f"Calculating batch metrics for user {user_id}, timeframe {timeframe}")
        
        metrics = {}
        
        # Calculate metrics
        metrics['sharpe_ratio'] = await self.calculate_and_cache_sharpe_ratio(user_id, timeframe)
        metrics['max_drawdown'] = await self.calculate_and_cache_max_drawdown(user_id, timeframe)
        metrics['var_95'] = await self.calculate_and_cache_var(user_id, 0.95, timeframe)
        metrics['var_99'] = await self.calculate_and_cache_var(user_id, 0.99, timeframe)
        
        logger.info(f"Completed batch metrics calculation for user {user_id}")
        return metrics
    
    async def cleanup_expired_cache(self) -> int:
        """Clean up expired cache entries"""
        with self.db_manager_factory() as db:
            deleted = db.purge_expired_metric_cache()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired cache entries")

        return deleted
    
    async def get_analytics_dashboard_data(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive analytics data for dashboard"""
        # Get recent portfolio snapshots
        recent_snapshots = await self.get_portfolio_history(user_id, 7)
        
        # Calculate or get cached metrics
        metrics = await self.calculate_portfolio_metrics_batch(user_id, "30d")
        
        # Get cached metrics summary
        user_key = self._user_id(user_id)
        with self.db_manager_factory() as db:
            cache_entries = db.list_active_metrics_cache(user_id=user_key)

        cached_metrics: Dict[str, Dict[str, Any]] = {}
        for entry in cache_entries:
            if entry.metric_type not in cached_metrics:
                cached_metrics[entry.metric_type] = {
                    'value': entry.value,
                    'calculated_at': entry.calculated_at.isoformat(),
                    'metadata': entry.metadata_payload or {},
                }
        
        return {
            'user_id': user_key,
            'recent_snapshots': recent_snapshots,
            'calculated_metrics': metrics,
            'cached_metrics': cached_metrics,
            'data_freshness': datetime.now().isoformat(),
            'snapshot_count': len(recent_snapshots)
        }
    
    async def schedule_analytics_calculation(self, user_ids: List[int] = None, interval_minutes: int = 15):
        """Schedule periodic analytics calculations"""
        logger.info(f"Starting scheduled analytics calculation (interval: {interval_minutes}min)")
        
        while True:
            try:
                # Clean up expired cache
                await self.cleanup_expired_cache()
                
                # Get user list if not provided
                target_user_ids = user_ids or self._snapshot_user_ids()
                
                # Calculate metrics for each user
                for user_key in target_user_ids:
                    try:
                        await self.calculate_portfolio_metrics_batch(user_key, "30d")
                    except Exception as e:
                        logger.error(f"Failed to calculate metrics for user {user_key}: {e}")
                
                logger.info(f"Completed scheduled analytics for {len(target_user_ids)} users")
                
                # Wait for next interval
                await asyncio.sleep(interval_minutes * 60)
                
            except Exception as e:
                logger.error(f"Error in scheduled analytics calculation: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying

class AnalyticsIntegrationManager:
    """Manager class for analytics database integration"""
    
    def __init__(self, db_manager_factory: Callable[[], DatabaseManager] = DatabaseManager):
        self.integrator = AnalyticsDBIntegrator(db_manager_factory)
        self.scheduler_task = None
    
    async def start(self):
        """Start the analytics integration system"""
        logger.info("Starting Analytics Database Integration Manager")
        
        # Start scheduled analytics calculation
        self.scheduler_task = asyncio.create_task(
            self.integrator.schedule_analytics_calculation(interval_minutes=15)
        )
        
        logger.info("Analytics Database Integration Manager started successfully")
    
    async def stop(self):
        """Stop the analytics integration system"""
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Analytics Database Integration Manager stopped")
    
    async def process_portfolio_update(self, user_id: int, portfolio_data: Dict[str, Any]):
        """Process a portfolio update and create snapshot"""
        snapshot_id = await self.integrator.create_portfolio_snapshot(user_id, portfolio_data)
        
        # Trigger metrics calculation for this user
        metrics = await self.integrator.calculate_portfolio_metrics_batch(user_id, "30d")
        
        return {
            'snapshot_id': snapshot_id,
            'metrics': metrics,
            'processed_at': datetime.now().isoformat()
        }
    
    async def get_user_analytics(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive analytics for a user"""
        return await self.integrator.get_analytics_dashboard_data(user_id)

# Test function
async def test_analytics_integration():
    """Test the analytics integration system"""
    print("🧪 Testing Analytics Database Integration...")
    
    manager = AnalyticsIntegrationManager()
    
    # Test portfolio update
    test_portfolio = {
        'total_value': 10000.0,
        'cash_balance': 2000.0,
        'positions_value': 8000.0,
        'unrealized_pnl': 500.0,
        'realized_pnl': 1000.0,
        'day_change': 250.0,
        'day_change_percent': 2.5,
        'positions': {
            'AAPL': {'quantity': 10, 'value': 1500.0},
            'GOOGL': {'quantity': 5, 'value': 2500.0}
        },
        'metrics': {}
    }
    
    # Process portfolio update
    result = await manager.process_portfolio_update(1, test_portfolio)
    print(f"✅ Portfolio update processed: {result}")
    
    # Get analytics
    analytics = await manager.get_user_analytics(1)
    print(f"📊 User analytics: {analytics}")
    
    print("🎉 Analytics integration test completed!")

if __name__ == "__main__":
    asyncio.run(test_analytics_integration())
