# 🤖 ASE BOT - Szczegółowa Dokumentacja Techniczna

**Wersja:** 4.3 | **Data:** 15 Grudnia 2025  
**Autor:** ASE BOT Trading System

---

## 📋 Spis Treści

1. [Architektura Systemu](#1-architektura-systemu)
2. [Auto Trader - Główny Silnik](#2-auto-trader---główny-silnik)
3. [System Sygnałów AI](#3-system-sygnałów-ai)
4. [Position Monitor](#4-position-monitor)
5. [Risk Management](#5-risk-management)
6. [Portfolio Manager](#6-portfolio-manager)
7. [CCXT Adapter](#7-ccxt-adapter)
8. [Economic Calendar](#8-economic-calendar)
9. [Baza Danych](#9-baza-danych)
10. [Konfiguracja i Uruchomienie](#10-konfiguracja-i-uruchomienie)

---

## 1. Architektura Systemu

### 1.1 Diagram Przepływu Danych

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ASE BOT TRADING SYSTEM                             │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         SIGNAL LAYER                                 │   │
│  │  ┌──────────────┐    ┌──────────────────────┐    ┌──────────────┐  │   │
│  │  │   titan_v3   │    │  COUNCIL V2.0        │    │  Built-in    │  │   │
│  │  │  (Supabase   │    │  (Fallback AI)       │    │  Strategies  │  │   │
│  │  │  Edge Func)  │    │  CIO+Exec+Research   │    │  Momentum/   │  │   │
│  │  │              │    │  +Risk Validation    │    │  MeanRevert  │  │   │
│  │  └──────┬───────┘    └──────────┬───────────┘    └──────┬───────┘  │   │
│  │         │                       │                        │          │   │
│  │         └───────────────────────┴────────────────────────┘          │   │
│  │                                 │                                    │   │
│  │                                 ▼                                    │   │
│  │                    ┌────────────────────────┐                       │   │
│  │                    │    trading_signals     │                       │   │
│  │                    │      (Supabase)        │                       │   │
│  │                    └────────────┬───────────┘                       │   │
│  └─────────────────────────────────┼───────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────▼───────────────────────────────────┐   │
│  │                          AUTO TRADER                                 │   │
│  │                                                                      │   │
│  │  1. Fetch Signals from trading_signals                              │   │
│  │  2. Validate (confidence, consensus, accuracy)                      │   │
│  │  3. Risk Assessment (Kelly, volatility, margin)                     │   │
│  │  4. Portfolio Analysis (diversification, limits)                    │   │
│  │  5. Position Sizing (adaptive to market regime)                     │   │
│  │  6. Execute Trade via CCXT Adapter                                  │   │
│  │                                                                      │   │
│  │  Loop: Every 300 seconds (5 minutes)                                │   │
│  └─────────────────────────────────┬───────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────▼───────────────────────────────────┐   │
│  │                       POSITION MONITOR                               │   │
│  │                                                                      │   │
│  │  Loop: Every 5 seconds                                              │   │
│  │                                                                      │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │ Trailing │ │ Dynamic  │ │ Partial  │ │ Time     │ │ Liqui-   │  │   │
│  │  │   Stop   │ │  SL/TP   │ │   TP     │ │  Exit    │ │ dation   │  │   │
│  │  │          │ │ Adjust   │ │ (3 lev)  │ │ (12h)    │ │ Protect  │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│  └─────────────────────────────────┬───────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────▼───────────────────────────────────┐   │
│  │                         CCXT ADAPTER                                 │   │
│  │                                                                      │   │
│  │  Supported: Binance (SPOT/MARGIN/FUTURES), Kraken, Bybit, OKX      │   │
│  │                                                                      │   │
│  │  • place_order(symbol, side, type, qty, price, sl, tp, leverage)   │   │
│  │  • close_position(symbol) - SPOT/MARGIN/FUTURES compatible         │   │
│  │  • get_positions() - Real-time from exchange                       │   │
│  │  • get_balance() - Multi-currency support                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Pliki Źródłowe

| Moduł | Plik | Linie | Opis |
|-------|------|-------|------|
| Auto Trader | `bot/auto_trader.py` | ~2500 | Główny silnik tradingowy |
| Position Monitor | `bot/services/position_monitor.py` | ~1500 | Monitoring SL/TP/trailing |
| Risk Manager | `bot/services/risk_manager.py` | ~400 | Kelly, position sizing |
| Portfolio Manager | `bot/services/portfolio_manager.py` | ~300 | Diversification, limits |
| CCXT Adapter | `bot/exchange_adapters/ccxt_adapter.py` | ~800 | Exchange interface |
| Economic Calendar | `bot/services/economic_calendar.py` | ~500 | News protection |
| Database | `bot/db.py` | ~600 | Supabase ORM |
| Security | `bot/security.py` | ~200 | API key encryption |

---

## 2. Auto Trader - Główny Silnik

### 2.1 Klasa `AutomatedTradingBot`

```python
class AutomatedTradingBot:
    """
    Główny silnik tradingowy.
    
    Atrybuty:
        user_id: UUID użytkownika
        exchange: Nazwa giełdy (binance, kraken)
        adapter: CCXTAdapter instance
        position_monitor: PositionMonitorService instance
        risk_manager: RiskManager instance
        portfolio_manager: PortfolioManager instance
    
    Konfiguracja:
        CYCLE_INTERVAL = 300  # 5 minut między cyklami
        TRUSTED_SOURCES = ['titan_v3', 'COUNCIL_V2.0_FALLBACK']
        MAX_POSITIONS = 5
        DAILY_TRADE_LIMIT = 15
    """
```

### 2.2 Główna Pętla Tradingowa

```python
async def run(self):
    """
    Główna pętla bota.
    
    while True:
        1. _run_trading_cycle()
        2. await asyncio.sleep(300)  # 5 min
    """

async def _run_trading_cycle(self):
    """
    Jeden cykl tradingowy:
    
    1. FETCH SIGNALS
       - Query trading_signals WHERE source IN TRUSTED_SOURCES
       - Filter: created_at > NOW() - 6 hours
       - Filter: action IN ('BUY', 'SELL')
    
    2. VALIDATE SIGNALS
       - Confidence threshold (adaptive 0.35-0.65)
       - Historical accuracy check
       - Consensus validation (if multiple sources)
    
    3. CHECK LIMITS
       - Max positions (5)
       - Daily trade limit (15)
       - Hourly limit (5)
       - Active margin check
    
    4. RISK ASSESSMENT
       - Kelly Criterion position size
       - Volatility adjustment
       - Market regime detection
    
    5. PORTFOLIO ANALYSIS
       - Single position limit (25% of equity)
       - Category exposure (40% max)
       - Stable reserve check (10% min)
    
    6. EXECUTE TRADES
       - place_order() via CCXT Adapter
       - Create position in database
       - Start monitoring
    
    7. MONITOR POSITIONS
       - position_monitor.check_all_positions()
    """
```

### 2.3 Walidacja Sygnałów

```python
async def _validate_signal(self, signal: dict) -> Tuple[bool, float, List[str]]:
    """
    Waliduje sygnał przed wykonaniem.
    
    Args:
        signal: Dict z polami: symbol, action, confidence, source, reasoning
    
    Returns:
        (execute: bool, score: float, reasons: List[str])
    
    Algorytm:
    ─────────
    1. BASE CONFIDENCE CHECK
       if signal.confidence < MIN_THRESHOLD (0.35):
           return (False, 0, ["Confidence too low"])
    
    2. HISTORICAL ACCURACY (jeśli >20 historycznych sygnałów)
       accuracy = successful_signals / total_signals
       if accuracy < 0.4:
           score *= 0.8  # Reduce trust
    
    3. CONSENSUS CHECK (jeśli multiple sources)
       matching_signals = count signals with same action
       if matching_signals >= 2:
           score *= 1.2  # Boost confidence
    
    4. MARKET REGIME ADJUSTMENT
       regime = detect_market_regime()  # bull/bear/sideways
       if regime == 'bear' and action == 'BUY':
           threshold += 0.1  # Require higher confidence
    
    5. FINAL DECISION
       if score >= threshold:
           return (True, score, reasons)
       else:
           return (False, score, reasons)
    """
```

### 2.4 Position Sizing

```python
async def _calculate_position_size(self, symbol, signal, balance):
    """
    Oblicza optymalną wielkość pozycji.
    
    Krok 1: BASE SIZE
    ─────────────────
    risk_per_trade = user_settings.risk_per_trade  # default 2%
    risk_amount = balance * (risk_per_trade / 100)
    
    Krok 2: STOP LOSS BASED SIZE
    ────────────────────────────
    sl_distance = get_stop_loss_distance(symbol)  # % od entry
    base_size = risk_amount / sl_distance
    
    Krok 3: KELLY CRITERION (jeśli >20 historycznych trade'ów)
    ─────────────────────────────────────────────────────────
    win_rate = calculate_win_rate(symbol)
    avg_win = calculate_avg_win(symbol)
    avg_loss = calculate_avg_loss(symbol)
    
    kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
    kelly = min(kelly, 0.25)  # Cap at 25%
    
    kelly_size = balance * (kelly / 2)  # Half-Kelly
    
    Krok 4: VOLATILITY ADJUSTMENT
    ─────────────────────────────
    volatility = calculate_realized_volatility(symbol, 20)  # 20 periods
    
    if volatility < 0.02:  # Low vol
        vol_multiplier = 1.2
    elif volatility > 0.05:  # High vol
        vol_multiplier = 0.7
    else:
        vol_multiplier = 1.0
    
    adjusted_size = min(base_size, kelly_size) * vol_multiplier
    
    Krok 5: CONFIDENCE SCALING
    ─────────────────────────
    final_size = adjusted_size * signal.confidence
    
    Krok 6: CAPS
    ────────────
    max_position = user_settings.max_position  # default $1000
    final_size = min(final_size, max_position, balance * 0.25)
    
    return final_size
    """
```

---

## 3. System Sygnałów AI

### 3.1 Źródła Sygnałów

| Source | Typ | Priorytet | Opis |
|--------|-----|-----------|------|
| `titan_v3` | Supabase Edge Function | 1 (Primary) | AI analysis z 200s timeout |
| `COUNCIL_V2.0_FALLBACK` | Multi-agent consensus | 2 (Fallback) | CIO + Exec + Research + Risk |

### 3.2 Struktura Sygnału

```python
@dataclass
class TradingSignal:
    """Sygnał z tabeli trading_signals."""
    
    id: UUID
    symbol: str              # "BTC/USDC", "ETH/USDT"
    action: str              # "BUY", "SELL", "HOLD"
    confidence: float        # 0.0 - 1.0
    source: str              # "titan_v3", "COUNCIL_V2.0_FALLBACK"
    reasoning: str           # AI explanation
    user_id: Optional[UUID]  # NULL = global, UUID = user-specific
    stop_loss: Optional[float]
    take_profit: Optional[float]
    expires_at: datetime
    created_at: datetime
```

### 3.3 COUNCIL V2.0 Fallback

```python
"""
COUNCIL V2.0 - Multi-Agent Consensus System

Agenci:
───────
1. CIO (Chief Investment Officer)
   - Strategy alignment
   - Expected Value calculation
   - Risk/Reward ratio (target 1:2+)

2. Execution Agent
   - TWAP deployment strategy
   - Slippage analysis
   - Order book depth

3. Research Agent
   - LTV (Lifetime Value) score
   - Halving/ETF catalysts
   - On-chain metrics

4. Risk Agent
   - Pre-trade checks
   - Position limits
   - Correlation analysis

Consensus:
──────────
- Wszystkie 4 agenty muszą PASS
- Jeden FAIL = sygnał odrzucony
- Confidence = avg(agent_scores)
"""
```

### 3.4 Tabela `trading_signals`

```sql
CREATE TABLE trading_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    action VARCHAR(10) NOT NULL CHECK (action IN ('BUY', 'SELL', 'HOLD')),
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    source VARCHAR(50) NOT NULL,
    reasoning TEXT,
    user_id UUID REFERENCES auth.users(id),  -- NULL = global
    stop_loss FLOAT,
    take_profit FLOAT,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Indexes
    INDEX idx_signals_symbol (symbol),
    INDEX idx_signals_source (source),
    INDEX idx_signals_created (created_at DESC)
);
```

---

## 4. Position Monitor

### 4.1 Klasa `PositionMonitorService`

```python
class PositionMonitorService:
    """
    Real-time position monitoring service.
    
    Wersja: 4.3
    Interwał: 5 sekund
    
    Funkcje:
    ────────
    1. Trailing Stop Loss
    2. Dynamic SL/TP adjustment
    3. Partial Take Profit (3 poziomy)
    4. Time-based exit (max 12h)
    5. Liquidation protection
    6. Hybrid RAM + Supabase persistence
    """
    
    # Configuration
    CHECK_INTERVAL = 5.0  # seconds
    MAX_POSITION_DURATION_HOURS = 12
    
    # Trailing Stop
    TRAILING_STOP_ACTIVATION = 0.5   # % profit to activate
    TRAILING_STOP_DISTANCE = 1.0     # % below peak
    
    # Partial Take Profit
    PARTIAL_TP_LEVELS = [
        (1.0, 0.25),   # 1% profit → sell 25%
        (2.0, 0.50),   # 2% profit → sell 50%
        (3.0, 0.75),   # 3% profit → sell 75%
    ]
    
    # Liquidation Protection
    LIQUIDATION_WARNING = 15.0       # % margin level
    LIQUIDATION_AUTO_CLOSE = 3.5     # % margin level
```

### 4.2 Główna Pętla Monitorowania

```python
async def _monitoring_loop(self):
    """
    Main monitoring loop.
    
    while self._running:
        for position in self.positions.values():
            try:
                # 1. Get current price
                price = await self._get_current_price(position.symbol)
                
                # 2. Check Stop Loss
                if await self._check_stop_loss(position, price):
                    continue  # Position closed
                
                # 3. Check Take Profit
                if await self._check_take_profit(position, price):
                    continue  # Position closed
                
                # 4. Check Trailing Stop
                if await self._check_trailing_stop(position, price):
                    continue  # Position closed
                
                # 5. Check Partial TP
                await self._check_partial_tp(position, price)
                
                # 6. Check Time Exit
                if await self._check_time_exit(position):
                    continue  # Position closed
                
                # 7. Check Liquidation Risk
                await self._check_liquidation_risk(position)
                
                # 8. Dynamic SL/TP Adjustment
                await self._adjust_sl_tp_if_needed(position, price)
                
            except Exception as e:
                logger.error(f"Error monitoring {position.symbol}: {e}")
        
        await asyncio.sleep(self.CHECK_INTERVAL)
    """
```

### 4.3 Algorytm Trailing Stop

```python
async def _check_trailing_stop(self, position, current_price):
    """
    Trailing Stop Logic:
    
    1. ACTIVATION CHECK
       ─────────────────
       side_multiplier = 1 if position.side == 'long' else -1
       profit_pct = (current_price - position.entry_price) / position.entry_price * 100
       profit_pct *= side_multiplier
       
       if profit_pct < TRAILING_ACTIVATION (0.5%):
           return False  # Not activated yet
    
    2. PEAK TRACKING
       ──────────────
       if not position.trailing_activated:
           position.trailing_activated = True
           position.peak_price = current_price
           position.trailing_sl = calculate_trailing_sl(current_price)
           logger.info(f"📈 Trailing activated at {profit_pct:.2f}%")
       
       # Update peak if new high (LONG) or new low (SHORT)
       if position.side == 'long' and current_price > position.peak_price:
           position.peak_price = current_price
           position.trailing_sl = current_price * (1 - TRAILING_DISTANCE/100)
       
       elif position.side == 'short' and current_price < position.peak_price:
           position.peak_price = current_price
           position.trailing_sl = current_price * (1 + TRAILING_DISTANCE/100)
    
    3. TRIGGER CHECK
       ──────────────
       if position.side == 'long' and current_price <= position.trailing_sl:
           await self._close_position(position, 'trailing_stop')
           return True
       
       elif position.side == 'short' and current_price >= position.trailing_sl:
           await self._close_position(position, 'trailing_stop')
           return True
       
       return False
    """
```

### 4.4 Algorytm Partial Take Profit

```python
async def _check_partial_tp(self, position, current_price):
    """
    Partial Take Profit - Zamyka część pozycji przy różnych level profit.
    
    PARTIAL_TP_LEVELS = [
        (1.0, 0.25),   # Level 1: 1% profit → sell 25%
        (2.0, 0.50),   # Level 2: 2% profit → sell 50%
        (3.0, 0.75),   # Level 3: 3% profit → sell 75%
    ]
    
    Algorytm:
    ─────────
    profit_pct = calculate_profit_pct(position, current_price)
    
    for level_idx, (target_profit, take_fraction) in enumerate(PARTIAL_TP_LEVELS):
        # Skip if already taken
        if position.partial_tp_taken.get(level_idx, False):
            continue
        
        # Check if profit threshold reached
        if profit_pct >= target_profit:
            # Calculate quantity to sell
            remaining_qty = position.quantity
            sell_qty = position.original_quantity * take_fraction
            sell_qty = min(sell_qty, remaining_qty * 0.9)  # Keep at least 10%
            
            # Execute partial close
            await self._execute_partial_close(position, sell_qty)
            
            # Mark level as taken
            position.partial_tp_taken[level_idx] = True
            position.quantity -= sell_qty
            
            # Save reevaluation
            await self._save_reevaluation(position, {
                'type': 'partial_tp',
                'level': level_idx + 1,
                'profit_pct': profit_pct,
                'qty_sold': sell_qty,
                'remaining': position.quantity
            })
            
            logger.info(f"💰 Partial TP Level {level_idx+1}: "
                       f"Sold {sell_qty:.6f} at {profit_pct:.2f}% profit")
    
    Przykład (LONG ETH, entry $3000, qty=1):
    ─────────────────────────────────────────
    Price $3030 (1%):
        Sell 0.25 ETH → remain 0.75 ETH
        Realized P&L: +$7.50
    
    Price $3060 (2%):
        Sell 0.375 ETH → remain 0.375 ETH
        Realized P&L: +$22.50
    
    Price $3090 (3%):
        Sell 0.28125 ETH → remain 0.09375 ETH
        Realized P&L: +$25.31
    
    Total Realized if all 3 levels hit: +$55.31
    Remaining 0.09375 ETH still in position for further gains
    """
```

### 4.5 Hybrid Persistence

```python
class HybridPersistence:
    """
    RAM + Supabase persistence for reliability.
    
    RAM (Primary):
    ──────────────
    - Fast access (~0ms)
    - All active positions in memory
    - Dict: position_id → Position object
    
    Supabase (Backup):
    ──────────────────
    - Persistent storage
    - Table: monitored_positions
    - Synced every 5 seconds
    
    Recovery on Restart:
    ────────────────────
    1. Load all OPEN positions from Supabase
    2. Reconcile with exchange positions
    3. Remove ghost positions
    4. Rebuild RAM cache
    """
    
    async def persist_position(self, position):
        """Save position to RAM and Supabase."""
        # RAM
        self.positions[position.id] = position
        
        # Supabase
        await self._upsert_to_supabase(position)
    
    async def restore_on_startup(self):
        """Restore positions from Supabase on bot restart."""
        db_positions = await self._load_from_supabase()
        exchange_positions = await self.adapter.get_positions()
        
        for pos in db_positions:
            # Check if still exists on exchange
            if self._position_exists_on_exchange(pos, exchange_positions):
                self.positions[pos.id] = pos
            else:
                # Ghost position - mark as closed
                await self._mark_as_closed(pos, 'ghost_cleanup')
```

---

## 5. Risk Management

### 5.1 Klasa `RiskManager`

```python
class RiskManager:
    """
    Zarządzanie ryzykiem pozycji.
    
    Algorytmy:
    ──────────
    1. Kelly Criterion
    2. Volatility-adjusted sizing
    3. Dynamic SL/TP based on ATR
    4. Market regime detection
    5. Correlation-aware limits
    """
```

### 5.2 Kelly Criterion

```python
def kelly_position_size(self, symbol, balance):
    """
    Optymalna wielkość pozycji według Kelly Criterion.
    
    Formula:
    ────────
    f* = (p × W - (1-p) × L) / W
    
    gdzie:
    - f* = fraction of bankroll to bet
    - p = probability of winning (win_rate)
    - W = average win size
    - L = average loss size
    
    Implementacja:
    ──────────────
    # Get historical stats
    trades = get_closed_trades(symbol, limit=50)
    
    if len(trades) < 20:
        return None  # Insufficient history
    
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    
    win_rate = len(wins) / len(trades)
    avg_win = sum(w.pnl for w in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(l.pnl for l in losses) / len(losses)) if losses else 0
    
    if avg_win == 0:
        return None
    
    kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
    
    # Caps
    kelly = max(0, min(kelly, 0.25))  # 0-25%
    
    # Half-Kelly (safer)
    half_kelly = kelly / 2
    
    return balance * half_kelly
    
    Przykład:
    ─────────
    balance = $10,000
    win_rate = 55%
    avg_win = $100
    avg_loss = $80
    
    kelly = (0.55 × 100 - 0.45 × 80) / 100
    kelly = (55 - 36) / 100 = 0.19 (19%)
    
    half_kelly = 0.095 (9.5%)
    position_size = $10,000 × 0.095 = $950
    """
```

### 5.3 Dynamic SL/TP

```python
async def calculate_dynamic_sl_tp(self, symbol, side, entry_price):
    """
    Dynamiczne SL/TP oparte na ATR i volatilności.
    
    Algorytm:
    ─────────
    # 1. Calculate ATR (Average True Range)
    candles = await self.adapter.fetch_ohlcv(symbol, '1h', limit=14)
    atr = calculate_atr(candles, period=14)
    
    # 2. Get market regime
    regime = self._detect_market_regime(candles)
    # 'trending', 'sideways', 'volatile'
    
    # 3. Set multipliers based on regime
    if regime == 'trending':
        sl_multiplier = 1.5   # Tighter SL
        tp_multiplier = 3.0   # Wider TP (let winners run)
    elif regime == 'sideways':
        sl_multiplier = 2.0   # Wider SL (avoid whipsaws)
        tp_multiplier = 2.0   # Tighter TP
    else:  # volatile
        sl_multiplier = 2.5   # Very wide SL
        tp_multiplier = 2.5   # Very wide TP
    
    # 4. Calculate SL/TP
    sl_distance = atr * sl_multiplier
    tp_distance = atr * tp_multiplier
    
    if side == 'long':
        stop_loss = entry_price - sl_distance
        take_profit = entry_price + tp_distance
    else:  # short
        stop_loss = entry_price + sl_distance
        take_profit = entry_price - tp_distance
    
    # 5. Apply user limits
    max_sl_pct = user_settings.stop_loss_pct or 5.0
    max_sl = entry_price * (1 - max_sl_pct/100) if side == 'long' else entry_price * (1 + max_sl_pct/100)
    
    stop_loss = max(stop_loss, max_sl) if side == 'long' else min(stop_loss, max_sl)
    
    return stop_loss, take_profit
    
    Przykład (BTC, trending, entry $100,000):
    ─────────────────────────────────────────
    ATR(14) = $1,500
    SL = $100,000 - ($1,500 × 1.5) = $97,750
    TP = $100,000 + ($1,500 × 3.0) = $104,500
    
    Risk:Reward = 1:2
    """
```

### 5.4 Market Regime Detection

```python
def _detect_market_regime(self, candles, lookback=20):
    """
    Wykrywa reżim rynku.
    
    Returns: 'bull', 'bear', 'sideways', 'volatile'
    
    Algorytm:
    ─────────
    closes = [c['close'] for c in candles[-lookback:]]
    
    # 1. Trend detection (Linear Regression Slope)
    slope = calculate_lr_slope(closes)
    
    # 2. Volatility (Standard Deviation)
    volatility = np.std(closes) / np.mean(closes)
    
    # 3. ADX (Average Directional Index)
    adx = calculate_adx(candles, period=14)
    
    # Decision
    if volatility > 0.05:
        return 'volatile'
    elif adx > 25:
        if slope > 0:
            return 'bull'
        else:
            return 'bear'
    else:
        return 'sideways'
    """
```

---

## 6. Portfolio Manager

### 6.1 Klasa `PortfolioManager`

```python
class PortfolioManager:
    """
    Portfolio-aware trading decisions.
    
    Limits:
    ───────
    max_single_position_pct = 25.0    # Max 25% in single asset
    max_category_exposure_pct = 40.0  # Max 40% in category (L1, DeFi)
    max_l1_exposure_pct = 400.0       # Max 400% leverage for L1s
    max_meme_exposure_pct = 10.0      # Max 10% in meme coins
    max_defi_exposure_pct = 50.0      # Max 50% in DeFi
    min_stable_reserve_pct = 10.0     # Min 10% in stablecoins
    concentration_warning = 0.7       # Warn at 70% concentration
    """
```

### 6.2 Trade Analysis

```python
def analyze_trade(self, symbol, action, proposed_size) -> dict:
    """
    Analizuje trade w kontekście portfolio.
    
    Returns:
        {
            'execute': bool,
            'size_multiplier': float,
            'reasons': List[str]
        }
    
    Algorytm:
    ─────────
    current_positions = self._get_current_positions()
    equity = self._calculate_equity()
    
    # 1. Single Position Limit (25%)
    position_pct = (proposed_size / equity) * 100
    if position_pct > self.max_single_position_pct:
        multiplier = self.max_single_position_pct / position_pct
        reasons.append(f"Reduced size: single position limit ({position_pct:.1f}% > 25%)")
    
    # 2. Category Exposure
    category = self._get_asset_category(symbol)  # L1, DeFi, Meme, etc.
    category_exposure = self._get_category_exposure(category)
    
    if category == 'meme' and category_exposure + position_pct > 10:
        return {'execute': False, 'reasons': ['Meme coin exposure limit']}
    
    # 3. Stable Reserve
    stable_balance = self._get_stable_balance()
    stable_pct = (stable_balance / equity) * 100
    
    if stable_pct < self.min_stable_reserve_pct:
        multiplier *= 0.5
        reasons.append(f"Stable reserve low ({stable_pct:.1f}%)")
    
    # 4. Concentration Risk
    hhi = self._calculate_herfindahl_index()  # 0-1
    if hhi > self.concentration_warning:
        multiplier *= 0.8
        reasons.append(f"High concentration risk (HHI: {hhi:.2f})")
    
    return {
        'execute': True,
        'size_multiplier': multiplier,
        'reasons': reasons
    }
    """
```

---

## 7. CCXT Adapter

### 7.1 Klasa `CCXTAdapter`

```python
class CCXTAdapter:
    """
    Unified exchange interface using CCXT library.
    
    Supported Exchanges:
    ────────────────────
    - binance (SPOT, MARGIN, FUTURES)
    - kraken (SPOT, FUTURES)
    - bybit
    - okx
    - bitget
    
    Trading Modes:
    ──────────────
    SPOT: No leverage, no reduceOnly
    MARGIN: Cross/Isolated, 3-10x leverage, reduceOnly supported
    FUTURES: Up to 125x leverage, full SL/TP support
    """
```

### 7.2 Place Order

```python
async def place_order(
    self,
    symbol: str,
    side: str,           # 'buy', 'sell'
    order_type: str,     # 'market', 'limit'
    quantity: float,
    price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    leverage: Optional[int] = None,
    reduce_only: bool = False
) -> dict:
    """
    Places order on exchange.
    
    Algorytm:
    ─────────
    # 1. Set leverage (FUTURES/MARGIN only)
    if leverage and self.trading_mode in ['futures', 'margin']:
        await self.exchange.set_leverage(leverage, symbol)
    
    # 2. Build order params
    params = {}
    
    if self.trading_mode == 'margin':
        params['marginMode'] = 'cross'  # or 'isolated'
    
    # 3. Handle reduceOnly
    if reduce_only:
        if self.trading_mode == 'spot':
            # SPOT doesn't support reduceOnly - skip
            pass
        else:
            params['reduceOnly'] = True
    
    # 4. Execute main order
    order = await self.exchange.create_order(
        symbol=symbol,
        type=order_type,
        side=side,
        amount=quantity,
        price=price,
        params=params
    )
    
    # 5. Set SL/TP (if supported)
    if stop_loss and self.trading_mode in ['futures', 'margin']:
        await self._set_stop_loss(symbol, stop_loss, quantity, side)
    
    if take_profit and self.trading_mode in ['futures', 'margin']:
        await self._set_take_profit(symbol, take_profit, quantity, side)
    
    return order
    """
```

### 7.3 Close Position

```python
async def close_position(self, symbol: str, reason: str = 'manual') -> dict:
    """
    Closes position - handles SPOT/MARGIN/FUTURES differences.
    
    Algorytm:
    ─────────
    position = await self.get_position(symbol)
    
    if not position:
        return {'status': 'no_position'}
    
    # Determine close side
    close_side = 'sell' if position.side == 'long' else 'buy'
    
    # Build params
    params = {}
    
    # SPOT MODE - No reduceOnly
    if self.trading_mode == 'spot':
        # Just sell the asset
        order = await self.exchange.create_market_order(
            symbol=symbol,
            side=close_side,
            amount=position.quantity
        )
    
    # MARGIN/FUTURES - Use reduceOnly
    else:
        params['reduceOnly'] = True
        
        if self.trading_mode == 'margin':
            params['marginMode'] = 'cross'
        
        order = await self.exchange.create_market_order(
            symbol=symbol,
            side=close_side,
            amount=position.quantity,
            params=params
        )
    
    return order
    """
```

---

## 8. Economic Calendar

### 8.1 News Protection

```python
class EconomicCalendarService:
    """
    Chroni przed tradingiem podczas ważnych wydarzeń makro.
    
    Events monitored:
    ─────────────────
    - FOMC (Federal Reserve) - HIGH impact
    - CPI (Consumer Price Index) - HIGH impact
    - NFP (Non-Farm Payrolls) - HIGH impact
    - PPI (Producer Price Index) - MEDIUM impact
    - GDP - HIGH impact
    - PCE - HIGH impact
    - Retail Sales - MEDIUM impact
    
    Protection Window:
    ──────────────────
    - 30 minutes before event
    - 60 minutes after event
    
    Behavior:
    ─────────
    - No new trades during window
    - Tighten SL on existing positions
    - Log warning to user
    """
```

### 8.2 Upcoming Event Check

```python
async def get_upcoming_economic_event(
    minutes_ahead: int = 30,
    min_impact: str = "high"
) -> Optional[Tuple[str, float]]:
    """
    Sprawdza czy zbliża się ważne wydarzenie.
    
    Returns:
        Tuple[event_name, minutes_until] or None
    
    Usage in auto_trader:
    ─────────────────────
    event = await get_upcoming_economic_event(30, "high")
    
    if event:
        name, minutes = event
        logger.warning(f"⚠️ {name} in {minutes:.0f} min - pausing trades")
        return  # Skip trading cycle
    """
```

---

## 9. Baza Danych

### 9.1 Schema

```sql
-- USERS
CREATE TABLE auth.users (
    id UUID PRIMARY KEY,
    email VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- API KEYS (encrypted)
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    exchange VARCHAR(20) NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    encrypted_api_secret TEXT NOT NULL,
    is_testnet BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- TRADING SETTINGS (per user)
CREATE TABLE trading_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) UNIQUE,
    risk_level INTEGER DEFAULT 5,
    risk_per_trade FLOAT DEFAULT 2.0,
    max_position FLOAT DEFAULT 1000,
    stop_loss_pct FLOAT DEFAULT 2.0,
    take_profit_pct FLOAT DEFAULT 10.0,
    leverage INTEGER DEFAULT 10,
    trailing_enabled BOOLEAN DEFAULT TRUE,
    partial_tp_enabled BOOLEAN DEFAULT TRUE,
    max_positions INTEGER DEFAULT 5,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- TRADES (closed positions)
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8),
    entry_price DECIMAL(20, 8),
    exit_price DECIMAL(20, 8),
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    pnl DECIMAL(20, 8),
    pnl_pct FLOAT,
    close_reason VARCHAR(50),
    source VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP
);

-- POSITIONS (open positions)
CREATE TABLE positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8),
    entry_price DECIMAL(20, 8),
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    leverage INTEGER,
    status VARCHAR(20) DEFAULT 'OPEN',
    created_at TIMESTAMP DEFAULT NOW()
);

-- MONITORED POSITIONS (Position Monitor cache)
CREATE TABLE monitored_positions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8),
    entry_price DECIMAL(20, 8),
    current_price DECIMAL(20, 8),
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    trailing_sl DECIMAL(20, 8),
    peak_price DECIMAL(20, 8),
    trailing_activated BOOLEAN DEFAULT FALSE,
    partial_tp_taken JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- POSITION REEVALUATIONS (SL/TP changes log)
CREATE TABLE position_reevaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    position_id UUID,
    user_id UUID REFERENCES auth.users(id),
    reevaluation_type VARCHAR(50),
    old_sl DECIMAL(20, 8),
    new_sl DECIMAL(20, 8),
    old_tp DECIMAL(20, 8),
    new_tp DECIMAL(20, 8),
    reason TEXT,
    action_taken VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- TRADING SIGNALS
CREATE TABLE trading_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    action VARCHAR(10) NOT NULL,
    confidence FLOAT,
    source VARCHAR(50) NOT NULL,
    reasoning TEXT,
    user_id UUID,
    stop_loss FLOAT,
    take_profit FLOAT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 10. Konfiguracja i Uruchomienie

### 10.1 Environment Variables (.env)

```bash
# Database (Required)
SUPABASE_DB_URL="postgresql://postgres:password@db.xxx.supabase.co:5432/postgres"
SUPABASE_URL="https://xxx.supabase.co"
SUPABASE_KEY="your_anon_key"

# Security (Required)
SECRET_KEY="your_32_byte_secret_key_here"
ENCRYPTION_KEY="your_fernet_key"

# Optional
LOG_LEVEL="INFO"
TELEGRAM_BOT_TOKEN="xxx"  # For alerts
```

### 10.2 Uruchomienie Botów

```bash
# 1. Boty tradingowe (5 użytkowników)
cd "/path/to/Algorytm Uczenia Kwantowego LLM"
python3 run_bots.py

# 2. Monitor wszystkich użytkowników
python3 monitor_group.py

# 3. Pojedynczy bot (specific user)
python3 -m bot.auto_trader --user-id=4177e228-e38e-4a64-b34a-2005a959fcf2
```

### 10.3 Logs

```
# Bot logs
2025-12-15 21:32:49 | INFO | multi_bot | 🤖 ASE BOT - Multi-User Trading System
2025-12-15 21:32:49 | INFO | multi_bot | 📅 Started at: 2025-12-15 21:32:49
2025-12-15 21:32:49 | INFO | multi_bot | 👥 Users: 5

# Trading logs
[12/15/25 21:31:18] INFO | 📊 Signal BTC/USDC: BUY confidence=0.38
[12/15/25 21:31:19] INFO | ⏭️ Signal skipped: Combined score 0.38 below threshold
[12/15/25 21:31:19] INFO | ✅ 0/1 signals passed validation

# Position Monitor logs
[12/15/25 21:31:21] INFO | 🔍 Reconciliation: Exchange has 6 active positions
[12/15/25 21:31:21] INFO | ✅ Reconciliation complete: No ghost positions
```

---

## 📚 Appendix

### A. Aktywni Użytkownicy

| User ID | Giełda | Tryb | Status |
|---------|--------|------|--------|
| `4177e228...` | Kraken | Futures | ✅ Active |
| `e4f7f9e4...` | Binance | MARGIN | ✅ Active |
| `b812b608...` | Kraken | Futures | ✅ Active |
| `1aa87e38...` | Kraken | Futures | ✅ Active |
| `43e88b0b...` | Binance | SPOT | ✅ Active |

### B. Error Codes

| Error | Cause | Solution |
|-------|-------|----------|
| `EOrder:Margin level too low` | Insufficient margin | Reduce position size |
| `EOrder:Insufficient funds` | Not enough balance | Deposit funds |
| `reduceOnly not valid` | SPOT mode | Use MARGIN/FUTURES |
| `Rate limit exceeded` | Too many API calls | Implement backoff |

---

**© 2025 ASE BOT Trading System**
