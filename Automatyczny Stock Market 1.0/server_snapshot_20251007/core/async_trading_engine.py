"""
Asynchronous Trading Engine 
Background tasks, queue system, parallel processing, non-blocking AI analysis
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import json
from collections import defaultdict
import weakref

# Queue and async imports
from asyncio import Queue, Event, Lock
import concurrent.futures

logger = logging.getLogger(__name__)

class TaskType(str, Enum):
    """Types of background tasks"""
    MARKET_DATA_COLLECTION = "market_data_collection"
    AI_ANALYSIS = "ai_analysis"
    PRICE_UPDATE = "price_update"
    POSITION_MONITORING = "position_monitoring"
    RISK_CHECK = "risk_check"
    ORDER_EXECUTION = "order_execution"
    STRATEGY_SIGNAL = "strategy_signal"
    BALANCE_UPDATE = "balance_update"

class TaskPriority(int, Enum):
    """Task priority levels"""
    CRITICAL = 1    # Order execution, risk checks
    HIGH = 2        # Price updates, position monitoring  
    MEDIUM = 3      # Strategy signals, AI analysis
    LOW = 4         # Balance updates, statistics

class TaskStatus(str, Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class BackgroundTask:
    """Background task definition"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: TaskType = TaskType.MARKET_DATA_COLLECTION
    priority: TaskPriority = TaskPriority.MEDIUM
    func: Optional[Callable] = None
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 30.0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    retries: int = 0
    dependencies: Set[str] = field(default_factory=set)
    callback: Optional[Callable] = None

class AsyncTradingEngine:
    """Advanced asynchronous trading engine with background processing"""
    
    def __init__(self):
        # Task management
        self.task_queues: Dict[TaskPriority, Queue] = {
            priority: Queue() for priority in TaskPriority
        }
        self.active_tasks: Dict[str, BackgroundTask] = {}
        self.completed_tasks: Dict[str, BackgroundTask] = weakref.WeakValueDictionary()
        self.task_results: Dict[str, Any] = {}
        
        # Engine state
        self.is_running = False
        self.workers: Dict[TaskPriority, List[asyncio.Task]] = defaultdict(list)
        self.worker_count = {
            TaskPriority.CRITICAL: 3,    # 3 workers for critical tasks
            TaskPriority.HIGH: 4,        # 4 workers for high priority
            TaskPriority.MEDIUM: 6,      # 6 workers for medium priority  
            TaskPriority.LOW: 2          # 2 workers for low priority
        }
        
        # Synchronization
        self.locks: Dict[str, Lock] = defaultdict(Lock)
        self.events: Dict[str, Event] = defaultdict(Event)
        
        # Performance tracking
        self.stats = {
            "tasks_submitted": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "avg_execution_time": 0.0,
            "queue_sizes": {},
            "worker_utilization": {}
        }
        
        # Market data management
        self.market_data_cache = {}
        self.price_subscriptions: Set[str] = set()
        self.last_price_update = {}
        
        # Strategy management
        self.active_strategies: Dict[str, Dict] = {}
        self.strategy_signals: Queue = Queue()
        
        # AI analysis management
        self.ai_analysis_queue: Queue = Queue()
        self.ai_results: Dict[str, Dict] = {}
        
        # Thread pool for CPU-intensive tasks
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="trading_engine"
        )

    async def start(self):
        """Start the async trading engine"""
        if self.is_running:
            logger.warning("Trading engine already running")
            return
        
        logger.info("🚀 Starting Async Trading Engine...")
        self.is_running = True
        
        # Start worker tasks for each priority level
        for priority in TaskPriority:
            worker_count = self.worker_count[priority]
            for i in range(worker_count):
                worker_task = asyncio.create_task(
                    self._worker_loop(priority, f"worker_{priority.value}_{i}")
                )
                self.workers[priority].append(worker_task)
        
        # Start background management tasks
        asyncio.create_task(self._statistics_loop())
        asyncio.create_task(self._market_data_loop())
        asyncio.create_task(self._ai_analysis_loop()) 
        asyncio.create_task(self._strategy_monitoring_loop())
        asyncio.create_task(self._cleanup_loop())
        
        logger.info(f"✅ Trading engine started with {sum(self.worker_count.values())} workers")

    async def stop(self):
        """Stop the trading engine gracefully"""
        logger.info("🛑 Stopping Async Trading Engine...")
        self.is_running = False
        
        # Cancel all worker tasks
        for priority_workers in self.workers.values():
            for worker in priority_workers:
                worker.cancel()
        
        # Wait for workers to finish
        await asyncio.sleep(1.0)
        
        # Close thread pool
        self.thread_pool.shutdown(wait=True)
        
        logger.info("✅ Trading engine stopped")

    async def submit_task(self, task: BackgroundTask) -> str:
        """Submit task for background execution"""
        try:
            # Validate task
            if not task.func:
                raise ValueError("Task must have a function to execute")
            
            # Check dependencies
            if task.dependencies:
                for dep_id in task.dependencies:
                    if dep_id not in self.completed_tasks:
                        dep_task = self.active_tasks.get(dep_id)
                        if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                            raise ValueError(f"Dependency {dep_id} not satisfied")
            
            # Add to appropriate queue
            await self.task_queues[task.priority].put(task)
            self.active_tasks[task.id] = task
            
            self.stats["tasks_submitted"] += 1
            
            logger.debug(f"📝 Task submitted: {task.id} ({task.task_type.value})")
            return task.id
            
        except Exception as e:
            logger.error(f"Task submission failed: {e}")
            task.status = TaskStatus.FAILED
            task.error = str(e)
            raise

    async def wait_for_task(self, task_id: str, timeout: float = 30.0) -> Any:
        """Wait for task completion and return result"""
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            task = self.active_tasks.get(task_id) or self.completed_tasks.get(task_id)
            
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            if task.status == TaskStatus.COMPLETED:
                return task.result
            elif task.status == TaskStatus.FAILED:
                raise RuntimeError(f"Task failed: {task.error}")
            elif task.status == TaskStatus.CANCELLED:
                raise asyncio.CancelledError("Task was cancelled")
            
            await asyncio.sleep(0.1)
        
        raise asyncio.TimeoutError(f"Task {task_id} timed out")

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending or running task"""
        task = self.active_tasks.get(task_id)
        
        if not task:
            return False
        
        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            return False
        
        task.status = TaskStatus.CANCELLED
        logger.info(f"❌ Task cancelled: {task_id}")
        return True

    # Worker implementation
    
    async def _worker_loop(self, priority: TaskPriority, worker_name: str):
        """Worker loop for processing tasks"""
        logger.debug(f"🔧 Worker {worker_name} started")
        
        while self.is_running:
            try:
                # Get task from queue (with timeout to allow shutdown)
                try:
                    task = await asyncio.wait_for(
                        self.task_queues[priority].get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process task
                await self._execute_task(task, worker_name)
                
            except Exception as e:
                logger.error(f"Worker {worker_name} error: {e}")
                await asyncio.sleep(0.5)
        
        logger.debug(f"🔧 Worker {worker_name} stopped")

    async def _execute_task(self, task: BackgroundTask, worker_name: str):
        """Execute a single task"""
        start_time = time.time()
        task.started_at = datetime.now()
        task.status = TaskStatus.RUNNING
        
        logger.debug(f"🔄 Executing task {task.id} on {worker_name}")
        
        try:
            # Set timeout
            result = await asyncio.wait_for(
                self._run_task_function(task),
                timeout=task.timeout
            )
            
            # Task completed successfully
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            
            # Store result
            self.task_results[task.id] = result
            
            # Call callback if provided
            if task.callback:
                try:
                    await task.callback(result)
                except Exception as e:
                    logger.warning(f"Task callback failed: {e}")
            
            # Update statistics
            execution_time = time.time() - start_time
            self.stats["tasks_completed"] += 1
            self._update_avg_execution_time(execution_time)
            
            logger.debug(f"✅ Task completed: {task.id} ({execution_time:.2f}s)")
            
        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.error = f"Task timed out after {task.timeout}s"
            self.stats["tasks_failed"] += 1
            logger.error(f"⏰ Task timeout: {task.id}")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            self.stats["tasks_failed"] += 1
            
            # Retry logic
            if task.retries < task.max_retries:
                task.retries += 1
                task.status = TaskStatus.PENDING
                
                # Add back to queue after delay
                await asyncio.sleep(task.retry_delay)
                await self.task_queues[task.priority].put(task)
                
                logger.warning(f"🔄 Retrying task {task.id} (attempt {task.retries})")
            else:
                logger.error(f"❌ Task failed permanently: {task.id} - {e}")
        
        finally:
            # Move to completed tasks (or keep in active if retrying)
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                self.completed_tasks[task.id] = task
                if task.id in self.active_tasks:
                    del self.active_tasks[task.id]

    async def _run_task_function(self, task: BackgroundTask) -> Any:
        """Run the task function with proper async handling"""
        func = task.func
        args = task.args
        kwargs = task.kwargs
        
        # Check if function is async
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            # Run in thread pool for blocking functions
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(self.thread_pool, func, *args, **kwargs)

    # Background loops and monitoring
    
    async def _statistics_loop(self):
        """Background statistics collection"""
        while self.is_running:
            try:
                # Update queue sizes
                self.stats["queue_sizes"] = {
                    priority.name: queue.qsize() 
                    for priority, queue in self.task_queues.items()
                }
                
                # Update worker utilization
                self.stats["worker_utilization"] = {
                    priority.name: len([w for w in workers if not w.done()])
                    for priority, workers in self.workers.items()
                }
                
                # Log statistics periodically
                if self.stats["tasks_completed"] > 0 and self.stats["tasks_completed"] % 100 == 0:
                    total_tasks = self.stats["tasks_submitted"]
                    completed = self.stats["tasks_completed"]
                    failed = self.stats["tasks_failed"]
                    success_rate = (completed / total_tasks) * 100 if total_tasks > 0 else 0
                    
                    logger.info(
                        f"📊 Engine Stats - Tasks: {total_tasks}, "
                        f"Success: {success_rate:.1f}%, "
                        f"Avg Time: {self.stats['avg_execution_time']:.2f}s"
                    )
                
                await asyncio.sleep(10.0)  # Update every 10 seconds
                
            except Exception as e:
                logger.error(f"Statistics loop error: {e}")
                await asyncio.sleep(30.0)

    async def _market_data_loop(self):
        """Background market data collection"""
        while self.is_running:
            try:
                # Process subscribed symbols
                for symbol in self.price_subscriptions:
                    # Submit market data collection task
                    task = BackgroundTask(
                        task_type=TaskType.MARKET_DATA_COLLECTION,
                        priority=TaskPriority.HIGH,
                        func=self._fetch_market_data,
                        args=(symbol,),
                        timeout=5.0
                    )
                    
                    await self.submit_task(task)
                
                # Wait before next collection cycle
                await asyncio.sleep(1.0)  # Collect every second
                
            except Exception as e:
                logger.error(f"Market data loop error: {e}")
                await asyncio.sleep(5.0)

    async def _ai_analysis_loop(self):
        """Background AI analysis processing"""
        while self.is_running:
            try:
                # Check if we have pending analysis requests
                if not self.ai_analysis_queue.empty():
                    analysis_request = await self.ai_analysis_queue.get()
                    
                    # Submit AI analysis task
                    task = BackgroundTask(
                        task_type=TaskType.AI_ANALYSIS,
                        priority=TaskPriority.MEDIUM,
                        func=self._perform_ai_analysis,
                        args=(analysis_request,),
                        timeout=30.0,
                        callback=self._handle_ai_analysis_result
                    )
                    
                    await self.submit_task(task)
                
                await asyncio.sleep(2.0)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"AI analysis loop error: {e}")
                await asyncio.sleep(10.0)

    async def _strategy_monitoring_loop(self):
        """Background strategy signal monitoring"""
        while self.is_running:
            try:
                # Process strategy signals
                if not self.strategy_signals.empty():
                    signal = await self.strategy_signals.get()
                    
                    # Submit strategy processing task
                    task = BackgroundTask(
                        task_type=TaskType.STRATEGY_SIGNAL,
                        priority=TaskPriority.HIGH,
                        func=self._process_strategy_signal,
                        args=(signal,),
                        timeout=10.0
                    )
                    
                    await self.submit_task(task)
                
                await asyncio.sleep(0.5)  # Fast processing for signals
                
            except Exception as e:
                logger.error(f"Strategy monitoring loop error: {e}")
                await asyncio.sleep(5.0)

    async def _cleanup_loop(self):
        """Background cleanup of completed tasks"""
        while self.is_running:
            try:
                # Remove old completed tasks to prevent memory leaks
                cutoff_time = datetime.now() - timedelta(hours=1)
                
                to_remove = []
                for task_id, task in self.completed_tasks.items():
                    if task.completed_at and task.completed_at < cutoff_time:
                        to_remove.append(task_id)
                
                for task_id in to_remove:
                    if task_id in self.task_results:
                        del self.task_results[task_id]
                
                logger.debug(f"🧹 Cleaned up {len(to_remove)} old tasks")
                
                await asyncio.sleep(300.0)  # Cleanup every 5 minutes
                
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
                await asyncio.sleep(600.0)

    # Task implementations
    
    async def _fetch_market_data(self, symbol: str) -> Dict[str, Any]:
        """Fetch market data for symbol"""
        # This method requires a real exchange API connection
        raise NotImplementedError("Market data fetching requires live exchange API integration")

    async def _perform_ai_analysis(self, analysis_request: Dict[str, Any]) -> Dict[str, Any]:
        """Perform AI market analysis"""
        # This method requires a real AI service integration
        raise NotImplementedError("AI analysis requires integration with a real AI service")

    async def _handle_ai_analysis_result(self, result: Dict[str, Any]):
        """Handle AI analysis result"""
        symbol = result.get("symbol")
        self.ai_results[symbol] = result
        
        logger.info(f"🤖 AI Analysis complete for {symbol}: {result.get('recommendation')}")

    async def _process_strategy_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Process trading strategy signal"""
        # This method requires real strategy implementation
        raise NotImplementedError("Strategy signal processing requires real trading strategy implementation")

    # Public interface methods
    
    async def subscribe_market_data(self, symbol: str):
        """Subscribe to market data for symbol"""
        self.price_subscriptions.add(symbol)
        logger.info(f"📊 Subscribed to market data: {symbol}")

    async def unsubscribe_market_data(self, symbol: str):
        """Unsubscribe from market data"""
        self.price_subscriptions.discard(symbol)
        logger.info(f"📊 Unsubscribed from market data: {symbol}")

    async def get_market_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest market data for symbol"""
        return self.market_data_cache.get(symbol)

    async def request_ai_analysis(self, symbol: str, analysis_type: str = "market_sentiment") -> str:
        """Request AI analysis (non-blocking)"""
        request_id = str(uuid.uuid4())
        analysis_request = {
            "id": request_id,
            "symbol": symbol,
            "type": analysis_type,
            "timestamp": datetime.now().isoformat()
        }
        
        await self.ai_analysis_queue.put(analysis_request)
        logger.info(f"🤖 AI analysis requested: {symbol} ({analysis_type})")
        return request_id

    async def get_ai_analysis_result(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest AI analysis result"""
        return self.ai_results.get(symbol)

    async def submit_strategy_signal(self, signal: Dict[str, Any]):
        """Submit strategy signal for processing"""
        await self.strategy_signals.put(signal)

    def _update_avg_execution_time(self, execution_time: float):
        """Update average execution time"""
        current_avg = self.stats["avg_execution_time"]
        completed_tasks = self.stats["tasks_completed"]
        
        if completed_tasks == 1:
            self.stats["avg_execution_time"] = execution_time
        else:
            # Rolling average
            self.stats["avg_execution_time"] = (
                (current_avg * (completed_tasks - 1) + execution_time) / completed_tasks
            )

    async def get_engine_stats(self) -> Dict[str, Any]:
        """Get comprehensive engine statistics"""
        return {
            "running": self.is_running,
            "stats": self.stats.copy(),
            "active_tasks": len(self.active_tasks),
            "market_subscriptions": len(self.price_subscriptions),
            "ai_analysis_queue": self.ai_analysis_queue.qsize(),
            "strategy_signals_queue": self.strategy_signals.qsize(),
            "worker_counts": self.worker_count,
            "cache_sizes": {
                "market_data": len(self.market_data_cache),
                "ai_results": len(self.ai_results)
            }
        }

# Global instance
async_trading_engine = AsyncTradingEngine()

# Convenience functions
async def get_trading_engine():
    """Get trading engine instance"""
    return async_trading_engine
