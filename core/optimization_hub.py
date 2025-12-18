"""
Integration Hub - Centralized optimization system coordination
Łączy wszystkie systemy optymalizacyjne: database, exchange, cache, trading engine, monitoring
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
import os
import sys
from pathlib import Path

# Import wszystkich systemów optymalizacyjnych
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.database_optimizer import DatabaseOptimizer, get_database_optimizer
from core.advanced_exchange_manager import AdvancedExchangeManager, get_exchange_manager  
from core.intelligent_cache_manager import IntelligentCacheManager, get_cache_manager
from core.async_trading_engine import AsyncTradingEngine, get_trading_engine
from monitoring.system_monitor import SystemMonitor, get_system_monitor

logger = logging.getLogger(__name__)

@dataclass
class OptimizationConfig:
    """Konfiguracja systemów optymalizacyjnych"""
    # Database optimization
    enable_database_optimization: bool = True
    database_pool_size: int = 20
    database_max_overflow: int = 30
    
    # Exchange management
    enable_exchange_management: bool = True
    max_exchanges: int = 5
    exchange_timeout: float = 30.0
    
    # Cache management
    enable_cache_management: bool = True
    cache_levels: int = 4
    redis_url: str = "redis://localhost:6379"
    
    # Trading engine
    enable_async_trading: bool = True
    worker_counts: Dict[str, int] = field(default_factory=lambda: {
        "critical": 3,
        "high": 4,
        "medium": 6,
        "low": 2
    })
    
    # System monitoring
    enable_monitoring: bool = True
    monitoring_interval: float = 10.0
    enable_prometheus: bool = True
    
    # Performance targets
    target_latency_ms: float = 50.0
    target_throughput_rps: int = 500
    memory_limit_gb: float = 14.0  # Reserve 2GB dla systemu

class OptimizationHub:
    """
    Centralny hub koordynujący wszystkie systemy optymalizacyjne
    Zarządza inicjalizacją, integracją i monitoringiem komponentów
    """
    
    def __init__(self, config: Optional[OptimizationConfig] = None):
        self.config = config or OptimizationConfig()
        
        # Komponenty optymalizacyjne
        self.database_optimizer: Optional[DatabaseOptimizer] = None
        self.exchange_manager: Optional[AdvancedExchangeManager] = None
        self.cache_manager: Optional[IntelligentCacheManager] = None  
        self.trading_engine: Optional[AsyncTradingEngine] = None
        self.system_monitor: Optional[SystemMonitor] = None
        
        # Stan systemu
        self.is_initialized = False
        self.is_running = False
        self.startup_time: Optional[datetime] = None
        self.components_status: Dict[str, str] = {}
        
        # Metryki integracji
        self.integration_stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "avg_response_time": 0.0,
            "components_initialized": 0
        }

    async def initialize(self) -> bool:
        """
        Inicjalizacja wszystkich systemów optymalizacyjnych
        Returns: True jeśli inicjalizacja przebiegła pomyślnie
        """
        if self.is_initialized:
            logger.warning("Optimization Hub already initialized")
            return True
        
        logger.info("🚀 Initializing Optimization Hub...")
        self.startup_time = datetime.now()
        
        try:
            # 1. Inicjalizacja Database Optimizer
            if self.config.enable_database_optimization:
                logger.info("📊 Initializing Database Optimizer...")
                self.database_optimizer = await get_database_optimizer()
                await self.database_optimizer.initialize(
                    pool_size=self.config.database_pool_size,
                    max_overflow=self.config.database_max_overflow
                )
                self.components_status["database_optimizer"] = "initialized"
                self.integration_stats["components_initialized"] += 1
                logger.info("✅ Database Optimizer initialized")
            
            # 2. Inicjalizacja Cache Manager
            if self.config.enable_cache_management:
                logger.info("🔄 Initializing Cache Manager...")
                self.cache_manager = await get_cache_manager()
                await self.cache_manager.initialize(
                    redis_url=self.config.redis_url,
                    levels=self.config.cache_levels
                )
                self.components_status["cache_manager"] = "initialized"
                self.integration_stats["components_initialized"] += 1
                logger.info("✅ Cache Manager initialized")
            
            # 3. Inicjalizacja Exchange Manager
            if self.config.enable_exchange_management:
                logger.info("🏦 Initializing Exchange Manager...")
                self.exchange_manager = await get_exchange_manager()
                await self.exchange_manager.initialize()
                self.components_status["exchange_manager"] = "initialized"
                self.integration_stats["components_initialized"] += 1
                logger.info("✅ Exchange Manager initialized")
            
            # 4. Inicjalizacja Trading Engine
            if self.config.enable_async_trading:
                logger.info("⚡ Initializing Async Trading Engine...")
                self.trading_engine = await get_trading_engine()
                
                # Konfiguracja worker counts
                for priority, count in self.config.worker_counts.items():
                    if hasattr(self.trading_engine, 'worker_count'):
                        # Mapowanie string priorities na enum values
                        priority_mapping = {
                            "critical": 1,
                            "high": 2, 
                            "medium": 3,
                            "low": 4
                        }
                        if priority in priority_mapping:
                            # self.trading_engine.worker_count[priority_mapping[priority]] = count
                            pass
                
                await self.trading_engine.start()
                self.components_status["trading_engine"] = "initialized"
                self.integration_stats["components_initialized"] += 1
                logger.info("✅ Trading Engine initialized")
            
            # 5. Inicjalizacja System Monitor
            if self.config.enable_monitoring:
                logger.info("🔍 Initializing System Monitor...")
                self.system_monitor = await get_system_monitor()
                self.system_monitor.monitor_interval = self.config.monitoring_interval
                await self.system_monitor.start_monitoring()
                self.components_status["system_monitor"] = "initialized"
                self.integration_stats["components_initialized"] += 1
                logger.info("✅ System Monitor initialized")
            
            # 6. Konfiguracja integracji między komponentami
            await self._configure_component_integration()
            
            # 7. Sprawdzenie inicjalizacji
            await self._validate_initialization()
            
            self.is_initialized = True
            initialization_time = (datetime.now() - self.startup_time).total_seconds()
            
            logger.info(f"🎉 Optimization Hub initialized successfully in {initialization_time:.2f}s")
            logger.info(f"📈 Components initialized: {self.integration_stats['components_initialized']}/5")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Optimization Hub initialization failed: {e}")
            self.components_status["initialization"] = f"failed: {e}"
            return False

    async def _configure_component_integration(self):
        """Konfiguracja integracji między komponentami"""
        logger.info("🔗 Configuring component integration...")
        
        try:
            # 1. Integracja Cache Manager z Database Optimizer
            if self.cache_manager and self.database_optimizer:
                # Cache manager będzie cache'ować wyniki zapytań do bazy
                self.database_optimizer.set_cache_manager(self.cache_manager)
                logger.debug("✅ Database-Cache integration configured")
            
            # 2. Integracja Exchange Manager z Cache Manager
            if self.exchange_manager and self.cache_manager:
                # Exchange manager będzie cache'ować dane rynkowe
                self.exchange_manager.set_cache_manager(self.cache_manager)
                logger.debug("✅ Exchange-Cache integration configured")
            
            # 3. Integracja Trading Engine z wszystkimi komponentami
            if self.trading_engine:
                if self.database_optimizer:
                    # Trading engine używa database optimizer do operacji DB
                    await self._integrate_trading_database()
                
                if self.exchange_manager:
                    # Trading engine używa exchange manager do operacji handlowych
                    await self._integrate_trading_exchange()
                
                if self.cache_manager:
                    # Trading engine używa cache manager do szybkiego dostępu do danych
                    await self._integrate_trading_cache()
            
            # 4. Integracja System Monitor z wszystkimi komponentami
            if self.system_monitor:
                await self._integrate_monitoring()
            
            logger.info("🔗 Component integration completed")
            
        except Exception as e:
            logger.error(f"Component integration failed: {e}")
            raise

    async def _integrate_trading_database(self):
        """Integracja Trading Engine z Database Optimizer"""
        try:
            # Konfiguracja callbacków dla operacji DB
            if hasattr(self.trading_engine, 'set_database_optimizer'):
                self.trading_engine.set_database_optimizer(self.database_optimizer)
            
            # Rejestracja metryk database w trading engine
            if self.system_monitor:
                self.system_monitor.add_metric_callback("db_operations", self._track_db_operations)
            
            logger.debug("✅ Trading-Database integration configured")
            
        except Exception as e:
            logger.error(f"Trading-Database integration failed: {e}")

    async def _integrate_trading_exchange(self):
        """Integracja Trading Engine z Exchange Manager"""
        try:
            # Subskrypcja danych rynkowych w trading engine
            if self.exchange_manager:
                # Przykładowe symbole do subskrypcji
                symbols = ["BTC/USDT", "ETH/USDT", "ADA/USDT", "DOT/USDT"]
                
                for symbol in symbols:
                    if hasattr(self.trading_engine, 'subscribe_market_data'):
                        await self.trading_engine.subscribe_market_data(symbol)
            
            logger.debug("✅ Trading-Exchange integration configured")
            
        except Exception as e:
            logger.error(f"Trading-Exchange integration failed: {e}")

    async def _integrate_trading_cache(self):
        """Integracja Trading Engine z Cache Manager"""
        try:
            # Konfiguracja cache dla trading decisions
            if self.cache_manager:
                # Definicja cache levels dla trading data
                trading_cache_config = {
                    "market_data": {"level": 1, "ttl": 5},      # 5 sekund dla danych rynkowych
                    "trading_signals": {"level": 2, "ttl": 30}, # 30 sekund dla sygnałów
                    "portfolio_data": {"level": 3, "ttl": 300}, # 5 minut dla danych portfolio
                    "historical_data": {"level": 4, "ttl": 3600} # 1 godzina dla danych historycznych
                }
                
                # Ustawienie konfiguracji cache
                for cache_type, config in trading_cache_config.items():
                    await self.cache_manager.set_cache_config(cache_type, config)
            
            logger.debug("✅ Trading-Cache integration configured")
            
        except Exception as e:
            logger.error(f"Trading-Cache integration failed: {e}")

    async def _integrate_monitoring(self):
        """Integracja System Monitor ze wszystkimi komponentami"""
        try:
            # Dodanie callbacków monitoringu dla każdego komponentu
            components = [
                ("database_optimizer", self.database_optimizer),
                ("exchange_manager", self.exchange_manager),
                ("cache_manager", self.cache_manager),
                ("trading_engine", self.trading_engine)
            ]
            
            for name, component in components:
                if component and hasattr(self.system_monitor, 'add_component_monitor'):
                    self.system_monitor.add_component_monitor(name, component)
            
            # Konfiguracja alertów specyficznych dla trading
            trading_alerts = {
                "trading_latency_high": {
                    "metric": "trading_api_latency_avg",
                    "threshold": self.config.target_latency_ms / 1000.0,
                    "operator": "gt",
                    "severity": "warning",
                    "message": "Trading latency above target: {value:.2f}s"
                },
                "memory_usage_trading": {
                    "metric": "system_memory_percent",
                    "threshold": (self.config.memory_limit_gb / 16.0) * 100,  # % of 16GB
                    "operator": "gt",
                    "severity": "warning",
                    "message": "Memory usage approaching limit: {value:.1f}%"
                }
            }
            
            # Dodanie alertów do systemu
            for alert_name, alert_config in trading_alerts.items():
                if hasattr(self.system_monitor, 'alert_rules'):
                    self.system_monitor.alert_rules[alert_name] = alert_config
            
            logger.debug("✅ Monitoring integration configured")
            
        except Exception as e:
            logger.error(f"Monitoring integration failed: {e}")

    async def _validate_initialization(self):
        """Walidacja poprawności inicjalizacji"""
        logger.info("🔍 Validating initialization...")
        
        validation_results = {}
        
        # Test Database Optimizer
        if self.database_optimizer:
            try:
                # Test connection pool
                pool_status = await self.database_optimizer.get_pool_status()
                validation_results["database_optimizer"] = pool_status.get("status", "unknown")
            except Exception as e:
                validation_results["database_optimizer"] = f"error: {e}"
        
        # Test Cache Manager
        if self.cache_manager:
            try:
                # Test Redis connection
                await self.cache_manager.set("test_key", "test_value", level=1)
                test_value = await self.cache_manager.get("test_key", level=1)
                validation_results["cache_manager"] = "ok" if test_value == "test_value" else "failed"
                await self.cache_manager.delete("test_key", level=1)
            except Exception as e:
                validation_results["cache_manager"] = f"error: {e}"
        
        # Test Exchange Manager
        if self.exchange_manager:
            try:
                # Test exchange connectivity
                exchanges = await self.exchange_manager.get_available_exchanges()
                validation_results["exchange_manager"] = f"ok ({len(exchanges)} exchanges)"
            except Exception as e:
                validation_results["exchange_manager"] = f"error: {e}"
        
        # Test Trading Engine
        if self.trading_engine:
            try:
                # Test engine stats
                stats = await self.trading_engine.get_engine_stats()
                validation_results["trading_engine"] = "ok" if stats.get("running") else "not running"
            except Exception as e:
                validation_results["trading_engine"] = f"error: {e}"
        
        # Test System Monitor
        if self.system_monitor:
            try:
                # Test health check
                health = self.system_monitor.get_system_health()
                validation_results["system_monitor"] = health.get("status", "unknown")
            except Exception as e:
                validation_results["system_monitor"] = f"error: {e}"
        
        # Podsumowanie walidacji
        failed_components = [name for name, status in validation_results.items() if "error" in str(status)]
        
        if failed_components:
            logger.warning(f"⚠️  Some components failed validation: {failed_components}")
        else:
            logger.info("✅ All components validated successfully")
        
        logger.info(f"🔍 Validation results: {validation_results}")
        
        return validation_results

    async def start(self) -> bool:
        """Start całego systemu optymalizacyjnego"""
        if not self.is_initialized:
            logger.error("Cannot start - system not initialized")
            return False
        
        if self.is_running:
            logger.warning("Optimization Hub already running")
            return True
        
        logger.info("▶️  Starting Optimization Hub...")
        
        try:
            # Start wszystkich komponentów
            start_tasks = []
            
            if self.trading_engine and hasattr(self.trading_engine, 'start'):
                start_tasks.append(self.trading_engine.start())
            
            if self.system_monitor and hasattr(self.system_monitor, 'start_monitoring'):
                start_tasks.append(self.system_monitor.start_monitoring())
            
            # Uruchomienie równoległe
            if start_tasks:
                await asyncio.gather(*start_tasks, return_exceptions=True)
            
            self.is_running = True
            logger.info("✅ Optimization Hub started successfully")
            
            # Start periodic health checks
            asyncio.create_task(self._health_check_loop())
            asyncio.create_task(self._performance_optimization_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Optimization Hub: {e}")
            return False

    async def stop(self) -> bool:
        """Zatrzymanie systemu optymalizacyjnego"""
        if not self.is_running:
            logger.warning("Optimization Hub not running")
            return True
        
        logger.info("⏹️  Stopping Optimization Hub...")
        
        try:
            # Stop wszystkich komponentów
            stop_tasks = []
            
            if self.trading_engine and hasattr(self.trading_engine, 'stop'):
                stop_tasks.append(self.trading_engine.stop())
            
            if self.system_monitor and hasattr(self.system_monitor, 'stop_monitoring'):
                stop_tasks.append(self.system_monitor.stop_monitoring())
            
            # Zatrzymanie równoległe
            if stop_tasks:
                await asyncio.gather(*stop_tasks, return_exceptions=True)
            
            # Cleanup connections
            if self.database_optimizer:
                await self.database_optimizer.cleanup()
            
            if self.cache_manager:
                await self.cache_manager.cleanup()
            
            self.is_running = False
            logger.info("✅ Optimization Hub stopped successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop Optimization Hub: {e}")
            return False

    async def _health_check_loop(self):
        """Okresowe sprawdzanie stanu systemu"""
        while self.is_running:
            try:
                # Sprawdzenie stanu komponentów
                health_status = await self.get_system_health()
                
                # Log status co 5 minut
                if datetime.now().minute % 5 == 0:
                    logger.info(f"🏥 System Health: {health_status['overall_status']}")
                
                # Trigger alerts jeśli potrzeba
                if health_status['overall_status'] in ['degraded', 'critical']:
                    logger.warning(f"⚠️  System health degraded: {health_status['issues']}")
                
                await asyncio.sleep(60.0)  # Check co minutę
                
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(300.0)  # Retry za 5 minut

    async def _performance_optimization_loop(self):
        """Automatyczne optymalizacje wydajności"""
        while self.is_running:
            try:
                # Zbieranie metryk wydajności
                perf_stats = await self.get_performance_stats()
                
                # Automatyczne optymalizacje
                if perf_stats.get('avg_latency_ms', 0) > self.config.target_latency_ms * 1.5:
                    logger.info("🔧 High latency detected - triggering optimizations")
                    await self._optimize_for_latency()
                
                if perf_stats.get('memory_usage_percent', 0) > 80:
                    logger.info("🧠 High memory usage - triggering cleanup")
                    await self._optimize_memory_usage()
                
                await asyncio.sleep(300.0)  # Optymalizuj co 5 minut
                
            except Exception as e:
                logger.error(f"Performance optimization error: {e}")
                await asyncio.sleep(600.0)

    async def _optimize_for_latency(self):
        """Optymalizacje dla zmniejszenia latencji"""
        try:
            # 1. Increase cache warming
            if self.cache_manager:
                await self.cache_manager.trigger_cache_warming()
            
            # 2. Optimize database connections
            if self.database_optimizer:
                await self.database_optimizer.optimize_connections()
            
            # 3. Adjust worker pool sizes
            if self.trading_engine:
                # Increase high-priority workers
                pass  # Implementation depends on trading engine API
            
            logger.info("⚡ Latency optimizations applied")
            
        except Exception as e:
            logger.error(f"Latency optimization failed: {e}")

    async def _optimize_memory_usage(self):
        """Optymalizacje użycia pamięci"""
        try:
            # 1. Cache cleanup
            if self.cache_manager:
                await self.cache_manager.cleanup_expired()
            
            # 2. Database connection cleanup
            if self.database_optimizer:
                await self.database_optimizer.cleanup_idle_connections()
            
            # 3. Trading engine cleanup
            if self.trading_engine and hasattr(self.trading_engine, '_cleanup_loop'):
                # Trigger immediate cleanup
                pass
            
            logger.info("🧹 Memory optimizations applied")
            
        except Exception as e:
            logger.error(f"Memory optimization failed: {e}")

    # Tracking methods
    async def _track_db_operations(self, operation_type: str, duration: float):
        """Track database operations"""
        self.integration_stats["total_requests"] += 1
        
        if duration < 1.0:  # Success threshold
            self.integration_stats["successful_requests"] += 1
        else:
            self.integration_stats["failed_requests"] += 1
        
        # Update average response time
        total_requests = self.integration_stats["total_requests"]
        current_avg = self.integration_stats["avg_response_time"]
        self.integration_stats["avg_response_time"] = (
            (current_avg * (total_requests - 1) + duration) / total_requests
        )

    # Public API methods
    
    async def get_system_health(self) -> Dict[str, Any]:
        """Pobierz stan całego systemu"""
        health_data = {
            "overall_status": "unknown",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": 0,
            "components": {},
            "issues": [],
            "performance": {}
        }
        
        if self.startup_time:
            health_data["uptime_seconds"] = (datetime.now() - self.startup_time).total_seconds()
        
        # Status komponentów
        components_healthy = 0
        total_components = 0
        
        for name, component in [
            ("database_optimizer", self.database_optimizer),
            ("exchange_manager", self.exchange_manager), 
            ("cache_manager", self.cache_manager),
            ("trading_engine", self.trading_engine),
            ("system_monitor", self.system_monitor)
        ]:
            if component:
                total_components += 1
                try:
                    if name == "system_monitor":
                        component_health = component.get_system_health()
                        status = component_health.get("status", "unknown")
                    else:
                        status = "healthy"  # Simplified status check
                    
                    health_data["components"][name] = status
                    
                    if status in ["healthy", "ok"]:
                        components_healthy += 1
                    elif status in ["degraded", "warning"]:
                        health_data["issues"].append(f"{name}: {status}")
                    else:
                        health_data["issues"].append(f"{name}: {status}")
                        
                except Exception as e:
                    health_data["components"][name] = f"error: {e}"
                    health_data["issues"].append(f"{name}: {e}")
        
        # Overall status
        if components_healthy == total_components:
            health_data["overall_status"] = "healthy"
        elif components_healthy > total_components * 0.7:
            health_data["overall_status"] = "degraded"
        else:
            health_data["overall_status"] = "critical"
        
        return health_data

    async def get_performance_stats(self) -> Dict[str, Any]:
        """Pobierz statystyki wydajności"""
        stats = {
            "timestamp": datetime.now().isoformat(),
            "integration_stats": self.integration_stats.copy(),
            "components_performance": {}
        }
        
        # Stats z każdego komponentu
        if self.system_monitor:
            try:
                perf_summary = self.system_monitor.get_performance_summary()
                stats["system_performance"] = perf_summary
            except Exception as e:
                stats["system_performance"] = {"error": str(e)}
        
        if self.trading_engine:
            try:
                engine_stats = await self.trading_engine.get_engine_stats()
                stats["trading_performance"] = engine_stats
            except Exception as e:
                stats["trading_performance"] = {"error": str(e)}
        
        if self.cache_manager:
            try:
                cache_stats = await self.cache_manager.get_cache_stats()
                stats["cache_performance"] = cache_stats
            except Exception as e:
                stats["cache_performance"] = {"error": str(e)}
        
        return stats

    async def get_component_status(self, component_name: str) -> Dict[str, Any]:
        """Pobierz status konkretnego komponentu"""
        component_map = {
            "database_optimizer": self.database_optimizer,
            "exchange_manager": self.exchange_manager,
            "cache_manager": self.cache_manager,
            "trading_engine": self.trading_engine,
            "system_monitor": self.system_monitor
        }
        
        component = component_map.get(component_name)
        if not component:
            return {"error": f"Component {component_name} not found"}
        
        try:
            status = {"name": component_name, "initialized": component is not None}
            
            # Component-specific status
            if component_name == "database_optimizer" and hasattr(component, 'get_pool_status'):
                status["pool_status"] = await component.get_pool_status()
                
            elif component_name == "cache_manager" and hasattr(component, 'get_cache_stats'):
                status["cache_stats"] = await component.get_cache_stats()
                
            elif component_name == "trading_engine" and hasattr(component, 'get_engine_stats'):
                status["engine_stats"] = await component.get_engine_stats()
                
            elif component_name == "system_monitor":
                status["health"] = component.get_system_health()
            
            return status
            
        except Exception as e:
            return {"error": f"Failed to get {component_name} status: {e}"}

# Global hub instance
optimization_hub = OptimizationHub()

# Convenience functions
async def initialize_optimization_hub(config: Optional[OptimizationConfig] = None) -> bool:
    """Inicjalizacja hub'a optymalizacji"""
    global optimization_hub
    
    if config:
        optimization_hub.config = config
    
    return await optimization_hub.initialize()

async def start_optimization_hub() -> bool:
    """Start hub'a optymalizacji"""
    return await optimization_hub.start()

async def stop_optimization_hub() -> bool:
    """Stop hub'a optymalizacji"""
    return await optimization_hub.stop()

async def get_optimization_hub() -> OptimizationHub:
    """Pobierz instancję hub'a"""
    return optimization_hub
