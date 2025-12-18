# 🤖 ASE BOT - Kompletna Dokumentacja Systemu

**Wersja:** 4.3 | **Data:** 15 Grudnia 2025  
**Autor:** ASE BOT Trading System

---

## 📋 Spis Treści

1. [Przegląd Systemu](#1-przegląd-systemu)
2. [Architektura](#2-architektura)
3. [Moduły i Komponenty](#3-moduły-i-komponenty)
4. [Algorytmy Tradingowe](#4-algorytmy-tradingowe)
5. [System Sygnałów](#5-system-sygnałów)
6. [Position Monitor](#6-position-monitor)
7. [Risk Management](#7-risk-management)
8. [Obsługiwane Giełdy](#8-obsługiwane-giełdy)
9. [Konfiguracja](#9-konfiguracja)
10. [Baza Danych](#10-baza-danych)

---

## 1. Przegląd Systemu

### 1.1 Czym jest ASE BOT?

ASE BOT to zaawansowany, wieloużytkownikowy system automatycznego tradingu kryptowalut z:
- **AI-powered signal generation** (titan_v3, COUNCIL V2.0)
- **Dynamic risk management** (trailing stops, partial TP, liquidation protection)
- **Multi-exchange support** (Binance, Kraken, Bybit, OKX)
- **Real-time monitoring** (WebSocket, 5s position checks)

### 1.2 Kluczowe Funkcje

| Funkcja | Opis |
|---------|------|
| 🤖 **Multi-User** | Obsługuje wielu użytkowników jednocześnie |
| 📊 **AI Signals** | Integracja z titan_v3, COUNCIL V2.0 FALLBACK |
| 🛡️ **Risk Management** | Kelly Criterion, Dynamic SL/TP, Volatility-adjusted sizing |
| 📈 **Position Monitor** | Trailing stops, partial TP, liquidation protection |
| 💾 **Hybrid Persistence** | RAM + Supabase dla niezawodności |
| 🔔 **Alerts** | Email notifications dla krytycznych zdarzeń |

### 1.3 Aktywni Użytkownicy

| User ID | Giełda | Tryb | Status |
|---------|--------|------|--------|
| `4177e228...` | Kraken | Spot/Futures | ✅ Active |
| `e4f7f9e4...` | Binance | MARGIN | ✅ Active |
| `b812b608...` | Kraken | Spot/Futures | ✅ Active |
| `1aa87e38...` | Kraken | Spot/Futures | ✅ Active |
| `43e88b0b...` | Binance | SPOT | ✅ Active |

---

## 2. Architektura

### 2.1 Diagram Wysokiego Poziomu

```
┌─────────────────────────────────────────────────────────────────┐
│                      ASE BOT TRADING SYSTEM                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│  │ Signal Layer │ ──▶ │  Auto Trader │ ──▶ │   Exchange   │    │
│  │  (AI/titan)  │     │   (Engine)   │     │   Adapter    │    │
│  └──────────────┘     └──────────────┘     └──────────────┘    │
│         │                    │                    │             │
│         │                    ▼                    │             │
│         │          ┌──────────────┐               │             │
│         │          │    Risk      │               │             │
│         │          │  Management  │               │             │
│         │          └──────────────┘               │             │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Position Monitor (5s interval)              │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────────┐ │   │
│  │  │Trailing │ │ Dynamic │ │ Partial │ │ Liquidation   │ │   │
│  │  │  Stop   │ │  SL/TP  │ │   TP    │ │  Protection   │ │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └───────────────┘ │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Supabase Database                     │   │
│  │   ┌────────┐ ┌────────┐ ┌────────┐ ┌─────────────────┐ │   │
│  │   │ trades │ │position│ │ orders │ │trading_signals  │ │   │
│  │   └────────┘ └────────┘ └────────┘ └─────────────────┘ │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Przepływ Danych

```
1. Signal Generation (titan_v3 / COUNCIL V2.0)
   ↓
2. Signal Validation (confidence threshold, consensus)
   ↓
3. Risk Assessment (Kelly, position sizing, margin check)
   ↓
4. Portfolio Analysis (diversification, exposure limits)
   ↓
5. Order Execution (place_order via CCXT)
   ↓
6. Position Monitoring (SL/TP/trailing every 5s)
   ↓
7. Trade Recording (trades table, P&L calculation)
```

---

## 3. Moduły i Komponenty

### 3.1 Core Modules

| Moduł | Plik | Funkcja |
|-------|------|---------|
| **Auto Trader** | `bot/auto_trader.py` | Główny silnik tradingowy |
| **Position Monitor** | `bot/services/position_monitor.py` | Monitoring pozycji, SL/TP |
| **Risk Manager** | `bot/services/risk_manager.py` | Zarządzanie ryzykiem |
| **CCXT Adapter** | `bot/exchange_adapters/ccxt_adapter.py` | Interfejs giełd |
| **Database** | `bot/db.py` | Warstwa persystencji |

### 3.2 Auto Trader (`auto_trader.py`)

**Główne funkcje:**

```python
class AutomatedTradingBot:
    """
    Główny silnik tradingowy - orchestruje cały proces.
    """
    
    # Konfiguracja źródeł sygnałów
    TRUSTED_SOURCES = ['titan_v3', 'COUNCIL_V2.0_FALLBACK']
    
    async def run(self):
        """Główna pętla tradingowa (300s cykl)"""
        
    async def _run_trading_cycle(self):
        """Jeden cykl tradingowy:
        1. Fetch signals from trading_signals table
        2. Validate signals (confidence, consensus)
        3. Check risk limits (max positions, daily limits)
        4. Execute trades via strategies
        5. Monitor positions
        """
        
    async def _fetch_signals_from_db(self):
        """Pobiera sygnały z tabeli trading_signals:
        - Filtruje po TRUSTED_SOURCES
        - Sprawdza czas (max 6h old)
        - Zwraca BUY/SELL signals
        """
        
    async def _validate_signal(self, signal):
        """Walidacja sygnału:
        - Confidence threshold (adaptive: 0.35-0.65)
        - Historical accuracy
        - Market conditions
        """
```

### 3.3 Position Monitor (`position_monitor.py`)

**Wersja:** 4.3 | **Interwał:** 5 sekund

```python
class PositionMonitorService:
    """
    Serwis monitorowania pozycji w czasie rzeczywistym.
    
    Funkcje:
    - Trailing Stop Loss
    - Dynamic SL/TP adjustment
    - Partial Take Profit (3 poziomy)
    - Time-based exit (max 12h)
    - Liquidation protection (warn 15%, close 3.5%)
    - Hybrid RAM + Supabase persistence
    """
    
    # Konfiguracja
    CHECK_INTERVAL = 5.0  # seconds
    
    # Trailing Stop
    TRAILING_STOP_ACTIVATION = 0.5  # Aktywacja po 0.5% profit
    TRAILING_STOP_DISTANCE = 1.0    # Odległość od peak (%)
    
    # Partial Take Profit
    PARTIAL_TP_LEVELS = [
        (1.0, 0.25),   # 1% profit → sell 25%
        (2.0, 0.50),   # 2% profit → sell 50%
        (3.0, 0.75),   # 3% profit → sell 75%
    ]
    
    # Liquidation Protection
    LIQUIDATION_WARNING_THRESHOLD = 15.0   # %
    LIQUIDATION_AUTO_CLOSE_THRESHOLD = 3.5  # %
```

### 3.4 Risk Manager (`risk_manager.py`)

```python
class RiskManager:
    """
    Zarządzanie ryzykiem pozycji.
    
    Algorytmy:
    1. Kelly Criterion - optymalna wielkość pozycji
    2. Volatility-adjusted sizing
    3. Dynamic SL/TP based on ATR
    4. Correlation-aware position limits
    """
    
    async def calculate_position_size(self, symbol, signal):
        """
        Oblicza optymalną wielkość pozycji:
        
        1. Kelly Criterion (jeśli >20 historycznych trade'ów):
           kelly_fraction = (win_rate * avg_win - (1-win_rate) * avg_loss) / avg_win
           
        2. Volatility Adjustment:
           vol_multiplier = 1 / (1 + realized_volatility)
           
        3. Confidence Adjustment:
           final_size = base_size * confidence * vol_multiplier
        """
        
    async def calculate_dynamic_sl_tp(self, symbol, side, entry_price):
        """
        Dynamiczne SL/TP oparte na ATR i volatilności:
        
        SL = entry ± (ATR * sl_multiplier)
        TP = entry ± (ATR * tp_multiplier * 1.5)
        
        Dostosowanie do reżimu rynku:
        - trending: SL tighter, TP wider
        - sideways: SL wider, TP tighter
        - volatile: Both wider
        """
```

---

## 4. Algorytmy Tradingowe

### 4.1 Signal Generation Flow

```
┌─────────────────────────────────────────────────────────┐
│                    SIGNAL SOURCES                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐         ┌────────────────────────┐   │
│  │   titan_v3   │         │   COUNCIL V2.0         │   │
│  │ (Primary AI) │         │ (Fallback Consensus)   │   │
│  │              │         │                        │   │
│  │ • Supabase   │         │ • CIO Analysis         │   │
│  │   Edge Func  │         │ • Execution Strategy   │   │
│  │ • 200s       │         │ • Research (LTV/halv)  │   │
│  │   timeout    │         │ • Risk Checks          │   │
│  └──────────────┘         └────────────────────────┘   │
│         │                          │                    │
│         └──────────┬───────────────┘                    │
│                    ▼                                    │
│         ┌──────────────────┐                           │
│         │ trading_signals  │                           │
│         │     (Supabase)   │                           │
│         └──────────────────┘                           │
│                    │                                    │
│                    ▼                                    │
│         ┌──────────────────┐                           │
│         │ Signal Validator │                           │
│         │                  │                           │
│         │ • Confidence     │                           │
│         │   threshold      │                           │
│         │   (adaptive)     │                           │
│         │ • Consensus      │                           │
│         │   check          │                           │
│         │ • Historical     │                           │
│         │   accuracy       │                           │
│         └──────────────────┘                           │
│                    │                                    │
│                    ▼                                    │
│         ┌──────────────────┐                           │
│         │  AUTO TRADER     │                           │
│         │  Execute Trade   │                           │
│         └──────────────────┘                           │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Position Sizing Algorithm

```python
def calculate_optimal_position_size(
    balance: float,
    risk_per_trade: float,  # % (np. 2%)
    stop_loss_pct: float,   # % od entry
    volatility: float,      # realized vol
    confidence: float,      # signal confidence (0-1)
    max_position: float     # max $ per position
) -> float:
    """
    Krok 1: Base Risk Amount
    ─────────────────────────
    risk_amount = balance * (risk_per_trade / 100)
    
    Krok 2: Position from SL
    ─────────────────────────
    position_from_sl = risk_amount / stop_loss_pct
    
    Krok 3: Volatility Adjustment
    ─────────────────────────────
    vol_multiplier = 1.2 if volatility < 0.02 else 0.8
    adjusted_size = position_from_sl * vol_multiplier
    
    Krok 4: Confidence Scaling
    ─────────────────────────
    final_size = adjusted_size * confidence
    
    Krok 5: Caps
    ────────────
    final_size = min(final_size, max_position, balance * 0.25)
    
    return final_size
    """
```

### 4.3 Trailing Stop Algorithm

```python
async def check_trailing_stop(position, current_price):
    """
    Trailing Stop Logic:
    
    1. Activation Check:
       ─────────────────
       profit_pct = (current - entry) / entry * 100
       if profit_pct >= TRAILING_ACTIVATION (0.5%):
           activate trailing
    
    2. Peak Tracking:
       ──────────────
       if current_price > position.peak_price:
           position.peak_price = current_price
           position.trailing_sl = peak * (1 - TRAIL_DISTANCE)
    
    3. Trigger Check:
       ──────────────
       if current_price <= position.trailing_sl:
           CLOSE POSITION (market order)
           reason = "trailing_stop"
    
    Example (LONG BTC):
    ───────────────────
    Entry: $100,000
    Activation: $100,500 (0.5% profit)
    Peak: $102,000
    Trailing SL: $100,980 (1% below peak)
    Trigger: Price drops to $100,980 → CLOSE
    """
```

### 4.4 Partial Take Profit Algorithm

```python
PARTIAL_TP_LEVELS = [
    (1.0, 0.25),   # Level 1: 1% profit → sell 25%
    (2.0, 0.50),   # Level 2: 2% profit → sell 50%  
    (3.0, 0.75),   # Level 3: 3% profit → sell 75%
]

async def check_partial_tp(position, current_price):
    """
    Partial Take Profit Logic:
    
    1. Calculate Profit %:
       profit_pct = (current - entry) / entry * 100
    
    2. Check Each Level:
       for target_profit, take_fraction in PARTIAL_TP_LEVELS:
           if profit_pct >= target_profit:
               if level not already taken:
                   sell_qty = position.quantity * take_fraction
                   execute_sell(sell_qty)
                   position.partial_tp_taken[level] = True
    
    Example (LONG ETH, entry $3000, qty=1):
    ────────────────────────────────────────
    Price $3030 (1%): Sell 0.25 ETH → remain 0.75 ETH
    Price $3060 (2%): Sell 0.375 ETH → remain 0.375 ETH
    Price $3090 (3%): Sell 0.28125 ETH → remain 0.09375 ETH
    """
```

---

## 5. System Sygnałów

### 5.1 Tabela `trading_signals`

```sql
CREATE TABLE trading_signals (
    id UUID PRIMARY KEY,
    symbol VARCHAR NOT NULL,           -- 'BTC/USDC'
    action VARCHAR NOT NULL,           -- 'BUY', 'SELL', 'HOLD'
    confidence FLOAT,                  -- 0.0 - 1.0
    source VARCHAR NOT NULL,           -- 'titan_v3', 'COUNCIL_V2.0_FALLBACK'
    reasoning TEXT,                    -- AI explanation
    user_id UUID,                      -- NULL = global, UUID = user-specific
    stop_loss FLOAT,                   -- suggested SL price
    take_profit FLOAT,                 -- suggested TP price
    expires_at TIMESTAMP,              -- signal expiration
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 5.2 Trusted Sources

```python
# auto_trader.py line 816
TRUSTED_SOURCES = ['titan_v3', 'COUNCIL_V2.0_FALLBACK']

# Removed sources (not reliable):
# - 'ai-scheduler'
# - 'ai-trading-signals'  
# - 'titan_v2'
# - 'manual'
```

### 5.3 Signal Validation

```python
class SignalValidator:
    """
    Adaptive confidence threshold based on:
    - Market volatility
    - Recent signal accuracy
    - Time of day (Asia/EU/US sessions)
    """
    
    # Thresholds
    MIN_CONFIDENCE = 0.35  # Minimum acceptable
    MAX_CONFIDENCE = 0.65  # For high-risk conditions
    
    def validate(self, signal) -> Tuple[bool, float, List[str]]:
        """
        Returns: (execute: bool, score: float, reasons: List[str])
        
        Validation steps:
        1. Confidence >= threshold
        2. Signal age < 6 hours
        3. Source in TRUSTED_SOURCES
        4. Historical accuracy check (if available)
        5. Consensus with other signals (if multiple)
        """
```

---

## 6. Position Monitor

### 6.1 Monitoring Loop

```python
async def _monitoring_loop(self):
    """
    Main monitoring loop (runs every 5 seconds):
    
    while running:
        for position in self.positions:
            1. Fetch current price
            2. Check Stop Loss trigger
            3. Check Take Profit trigger
            4. Check Trailing Stop
            5. Check Partial TP levels
            6. Check Time-based exit (12h max)
            7. Check Liquidation risk
            8. Save reevaluation (if changes)
            
        await asyncio.sleep(5)
    """
```

### 6.2 Liquidation Protection

```python
# Margin Level Monitoring
LIQUIDATION_WARNING_THRESHOLD = 15.0   # Warn at 15% margin level
LIQUIDATION_AUTO_CLOSE_THRESHOLD = 3.5  # Auto-close at 3.5%

async def check_liquidation_risk(self, position, margin_level):
    """
    Liquidation Risk Check:
    
    margin_level = (equity / used_margin) * 100
    
    if margin_level <= 3.5%:
        EMERGENCY CLOSE all positions
        send_critical_alert()
        
    elif margin_level <= 15%:
        send_warning_alert()
        reduce_position_size()
    """
```

### 6.3 Hybrid Persistence

```python
class PositionMonitorService:
    """
    Hybrid RAM + Supabase persistence:
    
    1. RAM (Primary):
       - Fast access
       - All active positions
       - self.positions dict
    
    2. Supabase (Backup):
       - Persistent storage
       - monitored_positions table
       - Sync every 5 seconds
    
    3. Recovery:
       - On bot restart: load from Supabase
       - Reconcile with exchange positions
       - Remove ghost positions
    """
    
    async def _persist_positions(self):
        """Save all positions to Supabase every 5s"""
        
    async def _restore_positions_from_supabase(self):
        """Load positions on startup"""
```

---

## 7. Risk Management

### 7.1 Risk Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `risk_per_trade` | 2% | Max risk per single trade |
| `max_position` | $1000 | Max position size in USD |
| `max_positions` | 5 | Max concurrent positions |
| `daily_trade_limit` | 15 | Max trades per day |
| `hourly_trade_limit` | 5 | Max trades per hour |
| `stop_loss` | 2-5% | Default SL (dynamic) |
| `take_profit` | 5-15% | Default TP (dynamic) |

### 7.2 Kelly Criterion

```python
def kelly_position_size(
    win_rate: float,      # Historical win rate (0-1)
    avg_win: float,       # Average winning trade
    avg_loss: float,      # Average losing trade (positive number)
    bankroll: float       # Total capital
) -> float:
    """
    Kelly Formula:
    ─────────────
    f* = (p × W - (1-p) × L) / W
    
    where:
    - f* = fraction of bankroll to bet
    - p = probability of winning (win_rate)
    - W = average win size
    - L = average loss size
    
    Half-Kelly (safer):
    ──────────────────
    position = bankroll × (f* / 2)
    
    Example:
    ────────
    win_rate = 0.55 (55%)
    avg_win = $100
    avg_loss = $80
    bankroll = $10,000
    
    f* = (0.55 × 100 - 0.45 × 80) / 100 = 0.19
    Half-Kelly = $10,000 × 0.095 = $950
    """
    
    kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
    kelly = max(0, min(kelly, 0.25))  # Cap at 25%
    return bankroll * (kelly / 2)  # Half-Kelly for safety
```

### 7.3 Portfolio Manager

```python
class PortfolioManager:
    """
    Portfolio-aware trading decisions.
    """
    
    limits = {
        'max_single_position_pct': 25.0,    # Max 25% in single asset
        'max_category_exposure_pct': 40.0,  # Max 40% in category (L1, DeFi)
        'max_l1_exposure_pct': 400.0,       # Max 400% leverage for L1s
        'max_meme_exposure_pct': 10.0,      # Max 10% in meme coins
        'max_defi_exposure_pct': 50.0,      # Max 50% in DeFi
        'min_stable_reserve_pct': 10.0,     # Min 10% in stablecoins
        'concentration_warning': 0.7        # Warn at 70% concentration
    }
    
    def analyze_trade(self, symbol, action, size):
        """
        Returns: {execute: bool, size_multiplier: float, reasons: List}
        
        Checks:
        1. Single position limit
        2. Category exposure
        3. Stable reserve
        4. Diversification score
        """
```

---

## 8. Obsługiwane Giełdy

### 8.1 Binance

| Tryb | Funkcje | Uwagi |
|------|---------|-------|
| **SPOT** | Buy/Sell, no leverage | No `reduceOnly` support |
| **MARGIN** | Cross/Isolated, 3-10x | `reduceOnly` supported |
| **FUTURES** | Up to 125x leverage | Full SL/TP support |

### 8.2 Kraken

| Tryb | Funkcje | Uwagi |
|------|---------|-------|
| **SPOT** | Buy/Sell | SL/TP via Position Monitor |
| **FUTURES** | Up to 50x | Leverage in params |

### 8.3 CCXT Adapter

```python
class CCXTAdapter:
    """
    Unified exchange interface using CCXT library.
    
    Supported exchanges:
    - binance
    - kraken
    - bybit
    - okx
    - bitget
    
    Key methods:
    - place_order(symbol, side, type, qty, price, sl, tp, leverage)
    - close_position(symbol)
    - get_positions(symbol)
    - get_balance()
    - get_market_price(symbol)
    """
```

---

## 9. Konfiguracja

### 9.1 Environment Variables

```bash
# .env file

# Database
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_key
SUPABASE_DB_URL=postgresql://user:pass@host:5432/postgres

# Security
SECRET_KEY=your_32_byte_secret_key

# Optional
LOG_LEVEL=INFO
TELEGRAM_BOT_TOKEN=xxx  # For alerts
```

### 9.2 User Settings (per user)

```python
# trading_settings table
{
    'user_id': 'uuid',
    'risk_level': 5,           # 1-10 scale
    'risk_per_trade': 2.0,     # %
    'max_position': 1000,      # USD
    'stop_loss_pct': 2.0,      # %
    'take_profit_pct': 10.0,   # %
    'leverage': 10,            # max leverage
    'trailing_enabled': True,
    'partial_tp_enabled': True,
    'max_positions': 5
}
```

---

## 10. Baza Danych

### 10.1 Schema Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        SUPABASE TABLES                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │   users     │    │  api_keys   │    │ trading_settings    │ │
│  │             │───▶│             │───▶│                     │ │
│  │ id          │    │ user_id     │    │ user_id             │ │
│  │ email       │    │ exchange    │    │ risk_level          │ │
│  │ created_at  │    │ api_key     │    │ max_position        │ │
│  └─────────────┘    │ api_secret  │    │ stop_loss_pct       │ │
│                     └─────────────┘    └─────────────────────┘ │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │   trades    │    │  positions  │    │ trading_signals     │ │
│  │             │    │             │    │                     │ │
│  │ symbol      │    │ symbol      │    │ symbol              │ │
│  │ side        │    │ side        │    │ action              │ │
│  │ entry_price │    │ entry_price │    │ confidence          │ │
│  │ exit_price  │    │ quantity    │    │ source              │ │
│  │ pnl         │    │ stop_loss   │    │ reasoning           │ │
│  │ close_reason│    │ take_profit │    │ expires_at          │ │
│  └─────────────┘    │ status      │    └─────────────────────┘ │
│                     └─────────────┘                             │
│                                                                  │
│  ┌─────────────────────────┐    ┌─────────────────────────────┐│
│  │ monitored_positions     │    │ position_reevaluations      ││
│  │                         │    │                             ││
│  │ symbol                  │    │ position_id                 ││
│  │ entry_price             │    │ reevaluation_type           ││
│  │ stop_loss               │    │ old_sl / new_sl             ││
│  │ take_profit             │    │ old_tp / new_tp             ││
│  │ trailing_sl             │    │ reason                      ││
│  │ is_active               │    │ action_taken                ││
│  └─────────────────────────┘    └─────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 10.2 Trades Table

```sql
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    symbol VARCHAR NOT NULL,
    side VARCHAR NOT NULL,  -- 'long', 'short'
    quantity DECIMAL,
    entry_price DECIMAL,
    exit_price DECIMAL,
    stop_loss DECIMAL,
    take_profit DECIMAL,
    pnl DECIMAL,
    close_reason VARCHAR,  -- 'stop_loss', 'take_profit', 'trailing_stop', 'manual'
    source VARCHAR,        -- 'position_monitor', 'manual'
    created_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP
);
```

---

## 📚 Appendix

### A. Log Messages Guide

| Log | Meaning |
|-----|---------|
| `🛑 STOP LOSS TRIGGERED` | Position closed by SL |
| `🎯 TAKE PROFIT HIT` | Position closed by TP |
| `📈 TRAILING STOP` | Trailing SL triggered |
| `💰 PARTIAL TP` | Partial position closed |
| `🚨 LIQUIDATION RISK` | Margin level critical |
| `📝 Saved reevaluation` | SL/TP update recorded |

### B. Error Codes

| Error | Cause | Solution |
|-------|-------|----------|
| `EOrder:Margin level too low` | Insufficient margin | Reduce position size |
| `EOrder:Insufficient funds` | Not enough balance | Check wallet |
| `reduceOnly not valid` | SPOT mode | Use MARGIN/FUTURES |
| `Rate limit exceeded` | Too many requests | Wait & retry |

---

**© 2025 ASE BOT Trading System**
