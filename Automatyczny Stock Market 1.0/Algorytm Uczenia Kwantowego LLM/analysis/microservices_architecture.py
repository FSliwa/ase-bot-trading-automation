"""
MICROSERVICES ARCHITECTURE DESIGN - DOCKER ORCHESTRATION
Projekt architektury mikrousług z separacją serwisów i orkiestracja Docker
"""

# ==================================================================================
# 🏗️ MICROSERVICES DECOMPOSITION STRATEGY
# ==================================================================================

class MicroservicesDecomposition:
    """
    Strategia podziału monolitycznej aplikacji na mikrousługi
    """
    
    CURRENT_MONOLITH_ANALYSIS = {
        "monolithic_issues": {
            "scalability": [
                "Entire application scales as one unit",
                "Resource waste - unused features consume resources",
                "Database becomes bottleneck for all operations",
                "Cannot optimize individual service performance"
            ],
            "deployment": [
                "Single point of failure for entire application",
                "All features must be deployed together",
                "Rollback affects entire system",
                "No independent service updates"
            ],
            "development": [
                "Large codebase difficult to navigate",
                "Team coordination bottlenecks",
                "Technology lock-in across all features",
                "Testing complexity increases exponentially"
            ],
            "reliability": [
                "One service failure brings down entire app",
                "No fault isolation",
                "Shared database creates cascading failures",
                "Difficult to implement circuit breakers"
            ]
        },
        
        "decomposition_boundaries": {
            "business_capabilities": [
                "User Management & Authentication",
                "Trading Execution & Order Management",
                "Market Data Processing & Distribution",
                "Portfolio Management & Analytics",
                "AI Analysis & Signal Generation",
                "Risk Management & Compliance",
                "Notification & Communication",
                "Audit & Logging"
            ],
            "data_ownership": [
                "User data (authentication, preferences)",
                "Trading data (orders, positions, fills)", 
                "Market data (prices, volumes, orderbooks)",
                "Analytics data (metrics, performance, reports)",
                "AI data (models, signals, predictions)",
                "Risk data (limits, alerts, events)",
                "Audit data (logs, compliance, security)"
            ],
            "transaction_boundaries": [
                "User session management",
                "Order lifecycle management",
                "Position management",
                "Portfolio calculation",
                "Risk assessment",
                "Market data subscription"
            ]
        }
    }
    
    # SERVICE DECOMPOSITION DESIGN
    SERVICE_ARCHITECTURE = {
        
        # 1. API GATEWAY SERVICE
        "api_gateway": {
            "responsibility": "Single entry point, routing, authentication, rate limiting",
            "technology_stack": {
                "framework": "Nginx + Kong Gateway / Envoy Proxy",
                "language": "Lua scripts for custom logic",
                "database": "Redis for rate limiting and session storage",
                "monitoring": "Prometheus + Grafana"
            },
            "features": [
                "Request routing and load balancing",
                "JWT authentication and authorization",
                "Rate limiting per user/IP/endpoint",
                "Request/response transformation",
                "API versioning support",
                "Circuit breaker pattern",
                "Request logging and metrics",
                "CORS handling",
                "SSL termination",
                "API documentation aggregation"
            ],
            "configuration": """
                # nginx.conf
                upstream user_service {
                    server user-service:8001;
                    server user-service:8002;
                }
                
                upstream trading_service {
                    server trading-service:8003;
                    server trading-service:8004;
                }
                
                location /api/v1/users {
                    proxy_pass http://user_service;
                    proxy_set_header X-Request-ID $request_id;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                }
                
                location /api/v1/trading {
                    proxy_pass http://trading_service;
                    proxy_set_header Authorization $http_authorization;
                    proxy_read_timeout 60s;
                }
            """
        },
        
        # 2. USER MANAGEMENT SERVICE
        "user_service": {
            "responsibility": "Authentication, authorization, user preferences, session management",
            "technology_stack": {
                "framework": "FastAPI with SQLAlchemy",
                "language": "Python 3.11+",
                "database": "PostgreSQL for user data",
                "cache": "Redis for sessions and tokens",
                "security": "JWT tokens with refresh mechanism"
            },
            "api_endpoints": [
                "POST /auth/login - User authentication",
                "POST /auth/logout - Session termination", 
                "POST /auth/refresh - Token refresh",
                "GET /users/profile - User profile",
                "PUT /users/profile - Update profile",
                "GET /users/preferences - User preferences",
                "PUT /users/preferences - Update preferences",
                "GET /users/api-keys - Exchange API keys",
                "POST /users/api-keys - Add API key",
                "DELETE /users/api-keys/{id} - Remove API key"
            ],
            "database_schema": """
                CREATE TABLE users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    username VARCHAR(50) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_verified BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    last_login_at TIMESTAMP,
                    failed_login_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP
                );
                
                CREATE TABLE user_preferences (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    risk_tolerance VARCHAR(20) DEFAULT 'MEDIUM',
                    default_order_size DECIMAL(10,2),
                    stop_loss_percentage DECIMAL(5,2) DEFAULT 5.0,
                    take_profit_percentage DECIMAL(5,2) DEFAULT 10.0,
                    notifications_enabled BOOLEAN DEFAULT TRUE,
                    theme VARCHAR(20) DEFAULT 'dark',
                    language VARCHAR(10) DEFAULT 'en',
                    timezone VARCHAR(50) DEFAULT 'UTC'
                );
                
                CREATE TABLE exchange_credentials (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    exchange VARCHAR(50) NOT NULL,
                    api_key_encrypted TEXT NOT NULL,
                    api_secret_encrypted TEXT NOT NULL,
                    passphrase_encrypted TEXT,
                    testnet BOOLEAN DEFAULT FALSE,
                    permissions TEXT[],
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_used_at TIMESTAMP
                );
            """,
            "docker_configuration": """
                # Dockerfile.user-service
                FROM python:3.11-slim
                
                WORKDIR /app
                
                COPY requirements.txt .
                RUN pip install --no-cache-dir -r requirements.txt
                
                COPY . .
                
                EXPOSE 8001
                
                CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
            """
        },
        
        # 3. TRADING SERVICE
        "trading_service": {
            "responsibility": "Order management, position tracking, trade execution, exchange integration",
            "technology_stack": {
                "framework": "FastAPI with AsyncIO",
                "language": "Python 3.11+ with asyncio",
                "database": "PostgreSQL with partitioning",
                "cache": "Redis for order status and real-time data",
                "message_queue": "RabbitMQ for order execution queue"
            },
            "api_endpoints": [
                "GET /positions - List active positions",
                "GET /positions/{id} - Get position details",
                "POST /positions/{id}/close - Close position",
                "GET /orders - List orders with filtering",
                "POST /orders - Place new order",
                "PUT /orders/{id} - Modify order",
                "DELETE /orders/{id} - Cancel order",
                "GET /orders/{id}/status - Order status",
                "GET /trades - Trade history",
                "GET /trades/{id} - Trade details",
                "POST /orders/bulk - Bulk order operations",
                "GET /exchanges/status - Exchange connectivity"
            ],
            "database_schema": """
                CREATE TABLE positions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    exchange VARCHAR(20) NOT NULL,
                    side VARCHAR(5) NOT NULL CHECK (side IN ('BUY', 'SELL')),
                    quantity DECIMAL(18,8) NOT NULL,
                    entry_price DECIMAL(18,8) NOT NULL,
                    current_price DECIMAL(18,8),
                    leverage DECIMAL(5,2) DEFAULT 1.0,
                    margin_used DECIMAL(18,8),
                    unrealized_pnl DECIMAL(18,8),
                    realized_pnl DECIMAL(18,8),
                    stop_loss DECIMAL(18,8),
                    take_profit DECIMAL(18,8),
                    status VARCHAR(20) DEFAULT 'OPEN',
                    strategy_id VARCHAR(50),
                    risk_score INTEGER,
                    entry_time TIMESTAMP DEFAULT NOW(),
                    exit_time TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                ) PARTITION BY HASH (user_id);
                
                CREATE TABLE orders (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL,
                    client_order_id VARCHAR(100) UNIQUE NOT NULL,
                    exchange_order_id VARCHAR(100),
                    symbol VARCHAR(20) NOT NULL,
                    exchange VARCHAR(20) NOT NULL,
                    side VARCHAR(5) NOT NULL CHECK (side IN ('BUY', 'SELL')),
                    order_type VARCHAR(20) NOT NULL,
                    quantity DECIMAL(18,8) NOT NULL,
                    price DECIMAL(18,8),
                    stop_price DECIMAL(18,8),
                    filled_quantity DECIMAL(18,8) DEFAULT 0,
                    remaining_quantity DECIMAL(18,8),
                    status VARCHAR(20) DEFAULT 'NEW',
                    time_in_force VARCHAR(10) DEFAULT 'GTC',
                    reduce_only BOOLEAN DEFAULT FALSE,
                    post_only BOOLEAN DEFAULT FALSE,
                    position_id UUID,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                ) PARTITION BY RANGE (created_at);
            """,
            "message_queue_integration": """
                # RabbitMQ Configuration
                import pika
                import json
                from typing import Dict, Any
                
                class OrderExecutionQueue:
                    def __init__(self):
                        self.connection = pika.BlockingConnection(
                            pika.ConnectionParameters('rabbitmq')
                        )
                        self.channel = self.connection.channel()
                        self.setup_queues()
                    
                    def setup_queues(self):
                        # Order execution queue
                        self.channel.queue_declare(
                            queue='order_execution',
                            durable=True,
                            arguments={'x-max-priority': 10}
                        )
                        
                        # Order status updates queue  
                        self.channel.queue_declare(
                            queue='order_updates',
                            durable=True
                        )
                        
                        # Dead letter queue for failed orders
                        self.channel.queue_declare(
                            queue='order_failed',
                            durable=True
                        )
                    
                    def publish_order(self, order_data: Dict[str, Any], priority: int = 5):
                        self.channel.basic_publish(
                            exchange='',
                            routing_key='order_execution',
                            body=json.dumps(order_data),
                            properties=pika.BasicProperties(
                                priority=priority,
                                delivery_mode=2  # Persistent
                            )
                        )
            """
        },
        
        # 4. MARKET DATA SERVICE
        "market_data_service": {
            "responsibility": "Real-time market data, price feeds, orderbook management, data distribution",
            "technology_stack": {
                "framework": "FastAPI with WebSockets",
                "language": "Python 3.11+ with asyncio",
                "database": "TimescaleDB for time-series data",
                "cache": "Redis Streams for real-time data",
                "websockets": "WebSocket connections to exchanges"
            },
            "api_endpoints": [
                "GET /tickers - Current market tickers",
                "GET /tickers/{symbol} - Specific ticker data",
                "GET /orderbook/{symbol} - Order book data",
                "GET /trades/{symbol} - Recent trades",
                "GET /candles/{symbol} - OHLCV candles",
                "POST /subscriptions - Subscribe to data feed",
                "DELETE /subscriptions/{id} - Unsubscribe",
                "WS /ws/market - Real-time market data WebSocket",
                "WS /ws/orderbook - Order book updates WebSocket",
                "GET /exchanges/status - Exchange connectivity status"
            ],
            "database_schema": """
                -- TimescaleDB hypertable for market data
                CREATE TABLE market_data (
                    time TIMESTAMPTZ NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    exchange VARCHAR(20) NOT NULL,
                    open_price DECIMAL(18,8),
                    high_price DECIMAL(18,8),
                    low_price DECIMAL(18,8),
                    close_price DECIMAL(18,8),
                    volume DECIMAL(18,8),
                    quote_volume DECIMAL(18,8),
                    trade_count INTEGER,
                    vwap DECIMAL(18,8)
                );
                
                -- Create hypertable for automatic partitioning
                SELECT create_hypertable('market_data', 'time', chunk_time_interval => INTERVAL '1 hour');
                
                -- Create indexes for fast queries
                CREATE INDEX idx_market_data_symbol_time ON market_data (symbol, time DESC);
                CREATE INDEX idx_market_data_exchange_time ON market_data (exchange, time DESC);
                
                -- Real-time ticker data (in-memory with Redis backup)
                CREATE TABLE current_tickers (
                    symbol VARCHAR(20) PRIMARY KEY,
                    exchange VARCHAR(20) NOT NULL,
                    bid DECIMAL(18,8),
                    ask DECIMAL(18,8),
                    last DECIMAL(18,8),
                    volume_24h DECIMAL(18,8),
                    change_24h DECIMAL(8,4),
                    high_24h DECIMAL(18,8),
                    low_24h DECIMAL(18,8),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """,
            "websocket_manager": """
                # WebSocket connection manager for real-time data
                import asyncio
                import json
                from typing import Dict, Set
                from fastapi import WebSocket
                import redis.asyncio as redis
                
                class MarketDataWebSocketManager:
                    def __init__(self):
                        self.active_connections: Dict[str, Set[WebSocket]] = {}
                        self.redis = redis.Redis(host='redis', port=6379, decode_responses=True)
                    
                    async def connect(self, websocket: WebSocket, symbol: str):
                        await websocket.accept()
                        if symbol not in self.active_connections:
                            self.active_connections[symbol] = set()
                        self.active_connections[symbol].add(websocket)
                        
                        # Start streaming data for this symbol
                        await self.start_symbol_stream(symbol)
                    
                    async def disconnect(self, websocket: WebSocket, symbol: str):
                        if symbol in self.active_connections:
                            self.active_connections[symbol].discard(websocket)
                            if not self.active_connections[symbol]:
                                del self.active_connections[symbol]
                                await self.stop_symbol_stream(symbol)
                    
                    async def broadcast_price_update(self, symbol: str, data: dict):
                        if symbol in self.active_connections:
                            message = json.dumps({
                                'type': 'price_update',
                                'symbol': symbol,
                                'data': data,
                                'timestamp': data.get('timestamp')
                            })
                            
                            # Remove disconnected WebSockets
                            disconnected = set()
                            for websocket in self.active_connections[symbol]:
                                try:
                                    await websocket.send_text(message)
                                except:
                                    disconnected.add(websocket)
                            
                            # Clean up disconnected WebSockets
                            for websocket in disconnected:
                                self.active_connections[symbol].discard(websocket)
                    
                    async def start_symbol_stream(self, symbol: str):
                        # Subscribe to Redis stream for this symbol
                        await self.redis.xadd(
                            f'market_subscriptions',
                            {'action': 'subscribe', 'symbol': symbol}
                        )
                    
                    async def stop_symbol_stream(self, symbol: str):
                        # Unsubscribe from Redis stream
                        await self.redis.xadd(
                            f'market_subscriptions',
                            {'action': 'unsubscribe', 'symbol': symbol}
                        )
            """
        },
        
        # 5. PORTFOLIO SERVICE  
        "portfolio_service": {
            "responsibility": "Portfolio analytics, performance metrics, risk calculations, reporting",
            "technology_stack": {
                "framework": "FastAPI with NumPy/Pandas",
                "language": "Python 3.11+ with scientific libraries",
                "database": "PostgreSQL + Redis for caching",
                "analytics": "NumPy, Pandas, SciPy for calculations",
                "caching": "Redis for computed metrics"
            },
            "api_endpoints": [
                "GET /portfolio/summary - Portfolio overview",
                "GET /portfolio/performance - Performance metrics",
                "GET /portfolio/allocation - Asset allocation",
                "GET /portfolio/risk - Risk metrics",
                "GET /portfolio/history - Historical performance",
                "GET /analytics/sharpe-ratio - Sharpe ratio calculation", 
                "GET /analytics/drawdown - Drawdown analysis",
                "GET /analytics/correlation - Correlation matrix",
                "GET /reports/daily - Daily performance report",
                "GET /reports/monthly - Monthly report",
                "POST /analytics/backtest - Strategy backtesting"
            ],
            "analytics_implementation": """
                # Advanced portfolio analytics
                import numpy as np
                import pandas as pd
                from scipy import stats
                from typing import Dict, List, Optional
                
                class PortfolioAnalytics:
                    def __init__(self, positions: List[dict], price_data: pd.DataFrame):
                        self.positions = positions
                        self.price_data = price_data
                        self.returns = self.calculate_returns()
                    
                    def calculate_returns(self) -> pd.Series:
                        # Calculate portfolio returns based on positions
                        portfolio_values = []
                        for timestamp in self.price_data.index:
                            total_value = 0
                            for position in self.positions:
                                symbol = position['symbol']
                                quantity = position['quantity']
                                price = self.price_data.loc[timestamp, symbol]
                                total_value += quantity * price
                            portfolio_values.append(total_value)
                        
                        portfolio_series = pd.Series(portfolio_values, index=self.price_data.index)
                        return portfolio_series.pct_change().dropna()
                    
                    def sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
                        excess_returns = self.returns - risk_free_rate / 252
                        return np.sqrt(252) * excess_returns.mean() / excess_returns.std()
                    
                    def sortino_ratio(self, risk_free_rate: float = 0.02) -> float:
                        excess_returns = self.returns - risk_free_rate / 252
                        downside_returns = excess_returns[excess_returns < 0]
                        downside_std = np.sqrt(np.mean(downside_returns**2))
                        return np.sqrt(252) * excess_returns.mean() / downside_std
                    
                    def max_drawdown(self) -> Dict[str, float]:
                        cumulative = (1 + self.returns).cumprod()
                        running_max = cumulative.cummax()
                        drawdown = (cumulative - running_max) / running_max
                        
                        max_dd = drawdown.min()
                        max_dd_end = drawdown.idxmin()
                        max_dd_start = running_max.loc[:max_dd_end].idxmax()
                        
                        return {
                            'max_drawdown': max_dd,
                            'start_date': max_dd_start.isoformat(),
                            'end_date': max_dd_end.isoformat(),
                            'duration_days': (max_dd_end - max_dd_start).days
                        }
                    
                    def value_at_risk(self, confidence: float = 0.05) -> float:
                        return np.percentile(self.returns, confidence * 100)
                    
                    def expected_shortfall(self, confidence: float = 0.05) -> float:
                        var = self.value_at_risk(confidence)
                        return self.returns[self.returns <= var].mean()
            """
        },
        
        # 6. AI ANALYSIS SERVICE
        "ai_service": {
            "responsibility": "AI model inference, signal generation, market analysis, model management",
            "technology_stack": {
                "framework": "FastAPI with ML libraries",
                "language": "Python 3.11+ with ML stack",
                "database": "PostgreSQL for model data + Vector DB",
                "ml_framework": "PyTorch/TensorFlow + Scikit-learn",
                "cache": "Redis for model predictions",
                "gpu_support": "CUDA support for model inference"
            },
            "api_endpoints": [
                "POST /analyze/market - Market sentiment analysis",
                "POST /analyze/symbol - Symbol-specific analysis",
                "POST /signals/generate - Generate trading signals",
                "GET /signals/history - Signal performance history",
                "GET /models/active - Active model information",
                "POST /models/predict - Direct model prediction",
                "GET /models/performance - Model performance metrics",
                "POST /training/start - Start model retraining",
                "GET /training/status - Training status",
                "POST /features/extract - Feature extraction"
            ],
            "model_management": """
                # AI Model Management System
                import torch
                import joblib
                import pandas as pd
                from typing import Dict, Any, List, Optional
                from datetime import datetime, timedelta
                
                class ModelManager:
                    def __init__(self):
                        self.models: Dict[str, Any] = {}
                        self.model_metadata: Dict[str, Dict] = {}
                        self.load_active_models()
                    
                    def load_active_models(self):
                        # Load models from database
                        active_models = self.get_active_models_from_db()
                        for model_info in active_models:
                            model_path = model_info['model_path']
                            model_name = model_info['model_name']
                            
                            if model_info['framework'] == 'pytorch':
                                model = torch.load(model_path, map_location='cpu')
                                if torch.cuda.is_available():
                                    model = model.cuda()
                            elif model_info['framework'] == 'sklearn':
                                model = joblib.load(model_path)
                            
                            self.models[model_name] = model
                            self.model_metadata[model_name] = model_info
                    
                    async def predict(self, model_name: str, features: pd.DataFrame) -> Dict[str, Any]:
                        if model_name not in self.models:
                            raise ValueError(f"Model {model_name} not found")
                        
                        model = self.models[model_name]
                        metadata = self.model_metadata[model_name]
                        
                        # Feature preprocessing
                        processed_features = self.preprocess_features(features, metadata)
                        
                        # Model prediction
                        if metadata['framework'] == 'pytorch':
                            with torch.no_grad():
                                prediction = model(processed_features).cpu().numpy()
                        else:
                            prediction = model.predict_proba(processed_features)
                        
                        return {
                            'prediction': prediction.tolist(),
                            'confidence': float(np.max(prediction)),
                            'model_version': metadata['version'],
                            'prediction_time': datetime.utcnow().isoformat()
                        }
                    
                    def evaluate_model_performance(self, model_name: str, 
                                                 period_days: int = 30) -> Dict[str, float]:
                        # Evaluate model performance over specified period
                        end_date = datetime.utcnow()
                        start_date = end_date - timedelta(days=period_days)
                        
                        # Get predictions and actual outcomes
                        predictions = self.get_predictions_from_db(model_name, start_date, end_date)
                        
                        if not predictions:
                            return {'accuracy': 0.0, 'precision': 0.0, 'recall': 0.0}
                        
                        # Calculate metrics
                        accuracy = sum(p['correct'] for p in predictions) / len(predictions)
                        
                        return {
                            'accuracy': accuracy,
                            'total_predictions': len(predictions),
                            'period_days': period_days,
                            'evaluation_time': datetime.utcnow().isoformat()
                        }
            """
        }
    }

# ==================================================================================
# 🐳 DOCKER ORCHESTRATION CONFIGURATION
# ==================================================================================

class DockerOrchestration:
    """
    Kompletna konfiguracja Docker Compose dla mikrousług
    """
    
    # DOCKER COMPOSE CONFIGURATION
    DOCKER_COMPOSE_YAML = """
version: '3.8'

services:
  # ========================
  # Infrastructure Services
  # ========================
  
  nginx-gateway:
    image: nginx:alpine
    container_name: api-gateway
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
    depends_on:
      - user-service
      - trading-service
      - market-data-service
      - portfolio-service
      - ai-service
    networks:
      - trading-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "nginx", "-t"]
      interval: 30s
      timeout: 10s
      retries: 3
  
  postgresql:
    image: postgres:15-alpine
    container_name: postgres-db
    environment:
      POSTGRES_DB: trading_platform
      POSTGRES_USER: trading_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/init:/docker-entrypoint-initdb.d
    ports:
      - "5432:5432"
    networks:
      - trading-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trading_user -d trading_platform"]
      interval: 30s
      timeout: 10s
      retries: 5
  
  timescaledb:
    image: timescale/timescaledb:latest-pg15
    container_name: timescale-db
    environment:
      POSTGRES_DB: market_data
      POSTGRES_USER: timescale_user
      POSTGRES_PASSWORD: ${TIMESCALE_PASSWORD}
    volumes:
      - timescale_data:/var/lib/postgresql/data
    ports:
      - "5433:5432"
    networks:
      - trading-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U timescale_user -d market_data"]
      interval: 30s
      timeout: 10s
      retries: 5
  
  redis:
    image: redis:7-alpine
    container_name: redis-cache
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
      - ./redis/redis.conf:/etc/redis/redis.conf
    command: redis-server /etc/redis/redis.conf
    networks:
      - trading-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
  
  rabbitmq:
    image: rabbitmq:3-management-alpine
    container_name: rabbitmq-broker
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}
      RABBITMQ_DEFAULT_VHOST: trading
    ports:
      - "5672:5672"
      - "15672:15672"  # Management UI
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    networks:
      - trading-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 30s
      timeout: 30s
      retries: 3
  
  # ========================
  # Application Services
  # ========================
  
  user-service:
    build:
      context: ./services/user-service
      dockerfile: Dockerfile
    container_name: user-service
    environment:
      - DATABASE_URL=postgresql://trading_user:${POSTGRES_PASSWORD}@postgresql:5432/trading_platform
      - REDIS_URL=redis://redis:6379
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
    ports:
      - "8001:8001"
    depends_on:
      - postgresql
      - redis
    networks:
      - trading-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
  
  trading-service:
    build:
      context: ./services/trading-service
      dockerfile: Dockerfile
    container_name: trading-service
    environment:
      - DATABASE_URL=postgresql://trading_user:${POSTGRES_PASSWORD}@postgresql:5432/trading_platform
      - REDIS_URL=redis://redis:6379
      - RABBITMQ_URL=amqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@rabbitmq:5672/trading
      - USER_SERVICE_URL=http://user-service:8001
      - MARKET_DATA_SERVICE_URL=http://market-data-service:8003
    ports:
      - "8002:8002"
    depends_on:
      - postgresql
      - redis
      - rabbitmq
      - user-service
    networks:
      - trading-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
  
  market-data-service:
    build:
      context: ./services/market-data-service
      dockerfile: Dockerfile
    container_name: market-data-service
    environment:
      - TIMESCALE_URL=postgresql://timescale_user:${TIMESCALE_PASSWORD}@timescaledb:5432/market_data
      - REDIS_URL=redis://redis:6379
      - EXCHANGE_API_KEYS=${EXCHANGE_API_KEYS}
    ports:
      - "8003:8003"
    depends_on:
      - timescaledb
      - redis
    networks:
      - trading-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8003/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
  
  portfolio-service:
    build:
      context: ./services/portfolio-service
      dockerfile: Dockerfile
    container_name: portfolio-service
    environment:
      - DATABASE_URL=postgresql://trading_user:${POSTGRES_PASSWORD}@postgresql:5432/trading_platform
      - REDIS_URL=redis://redis:6379
      - TRADING_SERVICE_URL=http://trading-service:8002
      - MARKET_DATA_SERVICE_URL=http://market-data-service:8003
    ports:
      - "8004:8004"
    depends_on:
      - postgresql
      - redis
      - trading-service
      - market-data-service
    networks:
      - trading-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8004/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '0.75'
          memory: 768M
        reservations:
          cpus: '0.5'
          memory: 512M
  
  ai-service:
    build:
      context: ./services/ai-service
      dockerfile: Dockerfile
    container_name: ai-service
    environment:
      - DATABASE_URL=postgresql://trading_user:${POSTGRES_PASSWORD}@postgresql:5432/trading_platform
      - REDIS_URL=redis://redis:6379
      - MODEL_STORAGE_PATH=/app/models
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - TAVILY_API_KEY=${TAVILY_API_KEY}
    ports:
      - "8005:8005"
    volumes:
      - ai_models:/app/models
    depends_on:
      - postgresql
      - redis
    networks:
      - trading-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8005/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      replicas: 1
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
  
  # ========================
  # Monitoring Services
  # ========================
  
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    networks:
      - trading-network
    restart: unless-stopped
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--web.enable-lifecycle'
  
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
    networks:
      - trading-network
    restart: unless-stopped

# ========================
# Networks and Volumes
# ========================

networks:
  trading-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16

volumes:
  postgres_data:
    driver: local
  timescale_data:
    driver: local
  redis_data:
    driver: local
  rabbitmq_data:
    driver: local
  ai_models:
    driver: local
  prometheus_data:
    driver: local
  grafana_data:
    driver: local
"""
    
    # ENVIRONMENT CONFIGURATION
    ENV_CONFIGURATION = """
# .env file for Docker Compose
POSTGRES_PASSWORD=your_secure_postgres_password
TIMESCALE_PASSWORD=your_secure_timescale_password
RABBITMQ_USER=trading_user
RABBITMQ_PASSWORD=your_secure_rabbitmq_password
JWT_SECRET_KEY=your_jwt_secret_key_here
ENCRYPTION_KEY=your_encryption_key_here
GRAFANA_PASSWORD=your_secure_grafana_password

# Exchange API Keys (encrypted)
EXCHANGE_API_KEYS=encrypted_api_keys_here

# External Services
GEMINI_API_KEY=your_gemini_api_key
TAVILY_API_KEY=your_tavily_api_key

# Service URLs (for internal communication)
USER_SERVICE_URL=http://user-service:8001
TRADING_SERVICE_URL=http://trading-service:8002
MARKET_DATA_SERVICE_URL=http://market-data-service:8003
PORTFOLIO_SERVICE_URL=http://portfolio-service:8004
AI_SERVICE_URL=http://ai-service:8005

# Performance Settings
MAX_WORKERS=4
WORKER_TIMEOUT=30
KEEPALIVE_TIMEOUT=5
"""

    # SERVICE MESH CONFIGURATION (Optional Advanced Setup)
    SERVICE_MESH_ISTIO = """
# Istio Service Mesh Configuration
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  name: trading-platform
spec:
  components:
    pilot:
      k8s:
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
    ingressGateways:
    - name: istio-ingressgateway
      enabled: true
      k8s:
        service:
          type: LoadBalancer
          ports:
          - port: 80
            name: http
          - port: 443
            name: https
  values:
    gateways:
      istio-ingressgateway:
        autoscaleEnabled: true
        autoscaleMin: 2
        autoscaleMax: 5
        cpu:
          targetAverageUtilization: 60
"""

if __name__ == "__main__":
    print("🏗️ MICROSERVICES ARCHITECTURE DESIGN")
    print("=" * 60)
    print("✅ Service decomposition strategy defined")
    print("🐳 Docker orchestration configuration created")
    print("📊 Complete microservices architecture designed")
    print("🔄 Inter-service communication patterns established")
    print("📈 Monitoring and scaling strategies implemented")
