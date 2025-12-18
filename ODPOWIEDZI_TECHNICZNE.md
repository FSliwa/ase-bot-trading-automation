# 🔍 ASE BOT - PEŁNA DOKUMENTACJA TECHNICZNA

**Data:** $(date)
**Wersja:** v4.0 (z DCA)

---

## 📚 SPIS TREŚCI

1. [Gdzie jest zapisywane SL/TP?](#1-gdzie-jest-zapisywane-sltp)
2. [Jak działa śledzenie SL i TP przez bota?](#2-jak-działa-śledzenie-sl-i-tp-przez-bota)
3. [Jak działa ustawianie dźwigni?](#3-jak-działa-ustawianie-dźwigni)
4. [Jak działa ustawianie wielkości pozycji?](#4-jak-działa-ustawianie-wielkości-pozycji)
5. [Jak działa ustawianie SL i TP?](#5-jak-działa-ustawianie-sl-i-tp)
6. [Jak działa sprawdzanie dostępnej waluty?](#6-jak-działa-sprawdzanie-dostępnej-waluty)
7. [Jak działa logika reewaluacji transakcji?](#7-jak-działa-logika-reewaluacji-transakcji)
8. [Jak działa logika wchodzenia w transakcje?](#8-jak-działa-logika-wchodzenia-w-transakcje)
9. [Gdzie bot zapisuje wykonane transakcje?](#9-gdzie-bot-zapisuje-wykonane-transakcje)
10. [Dlaczego pliki testowe vs komercyjne?](#10-dlaczego-pliki-testowe-vs-komercyjne)
11. [Luki techniczne, analityczne, logiczne](#11-luki-techniczne-analityczne-logiczne)
12. [Porównanie z najlepszymi botami](#12-porównanie-z-najlepszymi-botami)

---

## 1. Gdzie jest zapisywane SL/TP?

### 📍 Lokalizacje w kodzie:

#### A) Tabela `trading_signals` (Supabase)
**Plik:** `bot/db.py` linie 277-320
```python
class TradingSignal(Base):
    __tablename__ = "trading_signals"
    
    # Price targets
    price_target = Column(Numeric, nullable=True)
    stop_loss = Column(Numeric, nullable=True)      # ← SL zapisywany tutaj
    take_profit = Column(Numeric, nullable=True)    # ← TP zapisywany tutaj
    entry_price = Column(Numeric, nullable=True)
```

#### B) Tabela `positions` (Supabase)
**Plik:** `bot/db.py` linie 76-100
```python
class Position(Base):
    __tablename__ = "positions"
    
    stop_loss = Column(Float, nullable=True)   # ← SL na poziomie pozycji
    take_profit = Column(Float, nullable=True) # ← TP na poziomie pozycji
    leverage = Column(Float, nullable=False, default=1.0)
```

#### C) Tabela `trades` (Supabase)
**Plik:** `bot/db.py` linie 263-295
```python
class Trade(Base):
    __tablename__ = "trades"
    
    # L2 FIX v3.0: Add missing SL/TP/leverage fields
    stop_loss = Column(Float, nullable=True)      # SL użyty w trade
    take_profit = Column(Float, nullable=True)    # TP użyty w trade
    leverage = Column(Float, nullable=True)       # Leverage użyty
    entry_price = Column(Float, nullable=True)    # Cena wejścia
    exit_price = Column(Float, nullable=True)     # Cena wyjścia
```

#### D) Tabela `trading_settings` (ustawienia użytkownika)
```sql
stop_loss_percentage DECIMAL(5, 2) DEFAULT 5.0,
take_profit_percentage DECIMAL(5, 2) DEFAULT 10.0,
```

#### E) Tabela `risk_management_settings`
```sql
take_profit_percent DECIMAL(5, 2) DEFAULT 3.00,
stop_loss_percent DECIMAL(5, 2) DEFAULT 5.00,
```

### 📊 Przepływ danych SL/TP:
```
1. User Settings (trading_settings/risk_management_settings)
   ↓
2. RiskManager → calculates absolute SL/TP prices
   ↓
3. Signal (trading_signals) → stores planned SL/TP
   ↓
4. Position (positions) → stores actual SL/TP on position
   ↓
5. Trade (trades) → records SL/TP used at trade execution
```

---

## 2. Jak działa śledzenie SL i TP przez bota?

### 🎯 Główny komponent: `PositionMonitorService`
**Plik:** `bot/services/position_monitor.py`

### Architektura monitorowania:

```python
class PositionMonitorService:
    """
    Background service that monitors all active positions for SL/TP triggers.
    Runs independently from the main trading cycle.
    """
    
    def __init__(self, exchange_adapter, check_interval=5.0, ...):
        self.check_interval = 5.0  # ← Sprawdza co 5 sekund!
        self.enable_trailing = True
        self.enable_dynamic_sl = True
        self.enable_partial_tp = True
        self.enable_time_exit = True
        self.enable_auto_sl_tp = True
```

### Główna pętla monitorowania:

```python
async def _monitor_loop(self):
    """Main monitoring loop - runs every 5 seconds"""
    while self.running:
        try:
            await self._check_all_positions()  # ← Sprawdza wszystkie pozycje
            await asyncio.sleep(self.check_interval)  # 5 sekund
        except Exception as e:
            logger.error(f"Monitor error: {e}")
```

### Co jest sprawdzane:

1. **SL Trigger Check** (linki ~300-350):
```python
async def _check_sl_trigger(self, pos: MonitoredPosition, current_price: float):
    if pos.side == 'long':
        sl_hit = current_price <= pos.stop_loss
    else:  # short
        sl_hit = current_price >= pos.stop_loss
    
    if sl_hit:
        await self._execute_close(pos, "STOP_LOSS", current_price)
        if self.on_sl_triggered:
            await self.on_sl_triggered(pos, current_price)
```

2. **TP Trigger Check** (linki ~350-400):
```python
async def _check_tp_trigger(self, pos: MonitoredPosition, current_price: float):
    if pos.side == 'long':
        tp_hit = current_price >= pos.take_profit
    else:  # short
        tp_hit = current_price <= pos.take_profit
    
    if tp_hit:
        await self._execute_close(pos, "TAKE_PROFIT", current_price)
```

3. **Trailing Stop Update** (linki ~400-450):
```python
async def _update_trailing_stop(self, pos: MonitoredPosition, current_price: float):
    profit_percent = self._calculate_profit_percent(pos, current_price)
    
    if profit_percent >= self.trailing_config.activation_profit_percent:
        # Calculate new trailing SL
        if pos.side == 'long':
            new_sl = current_price * (1 - trailing_distance / 100)
            if new_sl > pos.stop_loss:  # Only move up, never down!
                pos.stop_loss = new_sl
```

4. **Time Exit** (max hold hours):
```python
async def _check_time_exit(self, pos: MonitoredPosition):
    hours_held = (datetime.now() - pos.opened_at).total_seconds() / 3600
    if hours_held >= pos.max_hold_hours:  # Default: 12h
        await self._execute_close(pos, "TIME_EXIT", current_price)
```

5. **Partial Take Profit**:
```python
DEFAULT_PARTIAL_TP_LEVELS = [
    {"profit_percent": 3.0, "close_percent": 40},  # Close 40% at +3%
    {"profit_percent": 5.0, "close_percent": 30},  # Close 30% at +5%
    {"profit_percent": 7.0, "close_percent": 30},  # Close remaining at +7%
]
```

### Integracja z auto_trader.py:

```python
# W auto_trader.py linia ~176
self.position_monitor = PositionMonitorService(
    exchange_adapter=self.exchange,
    check_interval=5.0,  # Check every 5 seconds
    on_sl_triggered=self._on_sl_triggered,
    on_tp_triggered=self._on_tp_triggered,
    on_partial_tp_triggered=self._on_partial_tp_triggered,
    on_time_exit_triggered=self._on_time_exit_triggered,
    enable_trailing=True,
    enable_dynamic_sl=True,
    enable_partial_tp=True,
    enable_time_exit=True,
    enable_auto_sl_tp=True,
)
await self.position_monitor.start()
```

---

## 3. Jak działa ustawianie dźwigni?

### 📊 Główny komponent: `RiskManagerService`
**Plik:** `bot/services/risk_manager.py`

### Konfiguracja dźwigni:

```python
@dataclass
class RiskLimits:
    max_leverage: float = 150.0  # Maksymalna dozwolona dźwignia
    max_position_size_pct: float = 20.0  # % equity per position
```

### Ustawianie dźwigni na giełdzie:

**Plik:** `bot/exchange_adapters/ccxt_adapter.py`

```python
async def set_leverage(self, symbol: str, leverage: float):
    """Set leverage for a symbol (futures/margin only)."""
    try:
        # Normalize symbol for exchange
        exchange_symbol = self._normalize_symbol(symbol)
        
        # Check if exchange supports leverage
        if self.futures:
            await self.exchange.set_leverage(leverage, exchange_symbol)
        elif self.margin:
            # For margin, leverage is implicit in position size
            pass
        
        logger.info(f"✅ Leverage set to {leverage}x for {symbol}")
        return True
    except Exception as e:
        logger.error(f"Failed to set leverage for {symbol}: {e}")
        return False
```

### Automatyczne dostosowanie dźwigni:

```python
async def get_max_leverage(self, symbol: str) -> float:
    """Get maximum allowed leverage for a symbol."""
    try:
        markets = await self.exchange.load_markets()
        if symbol in markets:
            market = markets[symbol]
            # Binance futures
            if 'limits' in market and 'leverage' in market['limits']:
                return market['limits']['leverage']['max']
        return 10.0  # Default fallback
    except:
        return 10.0
```

### W kontekście pozycji:

```python
# W Position model (db.py linia 87)
leverage = Column(Float, nullable=False, default=1.0)

# Przy tworzeniu pozycji (db.py linia 520)
def create_position(
    self,
    symbol: str,
    side: str,
    quantity: float,
    entry_price: float,
    leverage: float,  # ← Przekazywana dźwignia
    ...
):
    margin_used = abs(quantity * entry_price / max(leverage, 1e-9))
    position = Position(
        ...
        leverage=leverage,
        margin_used=margin_used,
        ...
    )
```

---

## 4. Jak działa ustawianie wielkości pozycji?

### 📊 Position Sizing Methods:

#### A) Podstawowe: Risk-Based Sizing
**Plik:** `bot/services/risk_manager.py` linia ~518

```python
def get_position_sizing_recommendation(
    self, 
    symbol: str, 
    entry_price: float,
    stop_loss: float, 
    current_equity: float,
    risk_per_trade_pct: float = 1.0
) -> Dict:
    """Calculate position size based on risk."""
    
    # Calculate risk per unit (odległość od SL)
    risk_per_unit = abs(entry_price - stop_loss)
    
    # Calculate risk amount (1% of equity = $10 on $1000)
    risk_amount = current_equity * (risk_per_trade_pct / 100)
    
    # Calculate quantity
    # Formuła: qty = risk_amount / risk_per_unit
    recommended_quantity = risk_amount / risk_per_unit
    
    # Apply position size limits
    max_by_equity = current_equity * (self.max_position_size_pct / 100)
    max_quantity = max_by_equity / entry_price
    
    return {
        "recommended_quantity": min(recommended_quantity, max_quantity),
        "max_quantity": max_quantity,
        "risk_amount": risk_amount,
        "method_used": "risk_based"
    }
```

#### B) Kelly Criterion (zaawansowane)
```python
@dataclass
class KellyConfig:
    enabled: bool = True
    fraction: float = 0.25  # Use 25% Kelly (fractional Kelly)
    min_trades_required: int = 5  # Need 5 trades for reliable stats
    fallback_risk_percent: float = 1.0

def calculate_kelly_position_size(
    self,
    win_rate: float,  # np. 0.55 = 55%
    avg_win: float,   # średni zysk
    avg_loss: float,  # średnia strata
    current_equity: float
) -> float:
    """
    Kelly Criterion: f* = (W × p - L × q) / (W × L)
    gdzie W = średni zysk, L = średnia strata, p = win_rate, q = 1-p
    """
    if win_rate <= 0 or avg_win <= 0 or avg_loss >= 0:
        return current_equity * 0.01  # 1% fallback
    
    p = win_rate
    q = 1 - win_rate
    W = avg_win
    L = abs(avg_loss)
    
    kelly_fraction = (W * p - L * q) / (W * L)
    kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%
    
    return current_equity * kelly_fraction * self.kelly_config.fraction
```

#### C) Volatility-Adjusted Sizing
```python
async def get_volatility_adjusted_size(
    self,
    symbol: str,
    base_size: float
) -> float:
    """Adjust position size based on volatility."""
    
    vol_profile = await self.get_volatility_profile(symbol)
    if not vol_profile:
        return base_size
    
    # High volatility = smaller position
    # Low volatility = larger position (or standard)
    multiplier = vol_profile.risk_multiplier
    
    return base_size * multiplier
```

#### D) Market Regime Sizing (v3.0)
**Plik:** `bot/core/market_regime_sizer.py`

```python
class MarketRegimeSizer:
    """Dynamic position sizing based on market regime."""
    
    def get_size_multiplier(self, regime: MarketRegime) -> float:
        """
        TRENDING = 1.5x (więcej)
        RANGING = 1.0x (standard)  
        VOLATILE = 0.5x (mniej)
        CRISIS = 0.2x (minimum)
        """
        multipliers = {
            MarketRegime.TRENDING: 1.5,
            MarketRegime.RANGING: 1.0,
            MarketRegime.VOLATILE: 0.5,
            MarketRegime.CRISIS: 0.2,
        }
        return multipliers.get(regime, 1.0)
```

---

## 5. Jak działa ustawianie SL i TP?

### 📊 Metody kalkulacji SL/TP:

#### A) Percentage-Based (domyślne)
**Plik:** `bot/auto_trader.py` linie ~700-730

```python
async def execute_ai_analysis(self, existing_market_data: Dict = None):
    # Get user SL/TP settings
    tp_sl_settings = self.get_user_tp_sl_settings()
    tp_pct = tp_sl_settings['take_profit_pct']  # np. 3%
    sl_pct = tp_sl_settings['stop_loss_pct']     # np. 5%
    
    # Calculate absolute prices
    if action == 'BUY':
        # For BUY: TP above current price, SL below
        sig['take_profit'] = round(current_price * (1 + tp_pct / 100), 8)
        sig['stop_loss'] = round(current_price * (1 - sl_pct / 100), 8)
    else:  # SELL (short)
        # For SELL: TP below current price, SL above
        sig['take_profit'] = round(current_price * (1 - tp_pct / 100), 8)
        sig['stop_loss'] = round(current_price * (1 + sl_pct / 100), 8)
```

#### B) ATR-Based (dynamiczne)
**Plik:** `bot/services/risk_manager.py`

```python
@dataclass
class DynamicSLTPConfig:
    enabled: bool = True
    use_atr: bool = True
    atr_multiplier_sl: float = 2.0   # SL at 2x ATR from entry
    atr_multiplier_tp: float = 3.0   # TP at 3x ATR (1:1.5 R:R)
    min_sl_percent: float = 1.0      # Minimum 1% SL
    max_sl_percent: float = 5.0      # Maximum 5% SL
    min_rr_ratio: float = 1.5        # Minimum Risk:Reward

async def calculate_dynamic_sl_tp(
    self,
    symbol: str,
    entry_price: float,
    side: str  # 'long' or 'short'
) -> Tuple[float, float]:
    """Calculate SL/TP based on ATR."""
    
    atr = await self.calculate_atr(symbol, period=14)
    if not atr:
        # Fallback to percentage
        return self._calculate_percentage_sl_tp(entry_price, side)
    
    # SL = entry ± (ATR × multiplier)
    # TP = entry ± (ATR × multiplier × R:R ratio)
    
    sl_distance = atr.atr_value * self.dynamic_sltp_config.atr_multiplier_sl
    tp_distance = atr.atr_value * self.dynamic_sltp_config.atr_multiplier_tp
    
    if side == 'long':
        stop_loss = entry_price - sl_distance
        take_profit = entry_price + tp_distance
    else:  # short
        stop_loss = entry_price + sl_distance
        take_profit = entry_price - tp_distance
    
    # Enforce min/max SL
    sl_percent = abs(entry_price - stop_loss) / entry_price * 100
    if sl_percent < self.min_sl_percent:
        sl_distance = entry_price * self.min_sl_percent / 100
    elif sl_percent > self.max_sl_percent:
        sl_distance = entry_price * self.max_sl_percent / 100
    
    return (stop_loss, take_profit)
```

#### C) Support/Resistance Based (AI)
**Plik:** `bot/analysis/advanced_analyzer.py`

```python
def _calculate_risk_params(
    self, 
    symbol: str, 
    action: str,
    neural: Optional[PredictionResult],
    order_flow: Optional[Dict]
) -> Tuple[float, float]:
    """Calculate stop loss and take profit levels."""
    
    if neural.support_levels and action == 'buy':
        # Place stop below nearest support
        base_stop_loss = min(base_stop_loss, neural.support_levels[-1] * 0.995)
    elif neural.resistance_levels and action == 'sell':
        # Place stop above nearest resistance
        base_stop_loss = max(base_stop_loss, neural.resistance_levels[0] * 1.005)
```

---

## 6. Jak działa sprawdzanie dostępnej waluty?

### 📊 Główna funkcja: `manage_capital()`
**Plik:** `bot/auto_trader.py`

```python
async def manage_capital(self) -> str:
    """
    Check available capital and select quote currency.
    Returns: quote currency to use (USDT, EUR, USD, etc.)
    """
    
    try:
        # Fetch balance from exchange
        balance = await self.exchange.fetch_balance()
        
        # Priority: USDT > EUR > USD
        quote_currencies = ['USDT', 'EUR', 'USD']
        
        for quote in quote_currencies:
            if quote in balance['free']:
                free_balance = balance['free'][quote]
                if free_balance > 10:  # Min $10 to trade
                    logger.info(f"💰 Available capital: {free_balance:.2f} {quote}")
                    return quote
        
        logger.warning("No sufficient balance found")
        return 'USDT'  # Default fallback
        
    except Exception as e:
        logger.error(f"Failed to fetch balance: {e}")
        return 'USDT'
```

### Sprawdzanie przed transakcją:

```python
async def check_risk_limits(self) -> bool:
    """Check if we're within risk limits."""
    
    try:
        # 1. Check available balance
        balance = await self.exchange.fetch_balance()
        total_equity = balance['total'].get('USDT', 0)
        free_margin = balance['free'].get('USDT', 0)
        
        # 2. Check open positions count
        positions = await self.exchange.fetch_positions()
        open_positions = len([p for p in positions if p['contracts'] > 0])
        
        if open_positions >= self.max_positions:
            logger.warning(f"Max positions reached: {open_positions}/{self.max_positions}")
            return False
        
        # 3. Check daily loss
        if self.daily_loss_tracker:
            if not self.daily_loss_tracker.can_open_new_trade(self.user_id):
                logger.warning("Daily loss limit reached")
                return False
        
        # 4. Check minimum balance
        if free_margin < 10:
            logger.warning(f"Insufficient margin: ${free_margin}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Risk check failed: {e}")
        return False
```

---

## 7. Jak działa logika reewaluacji transakcji?

### 📊 Reewaluacja odbywa się na 3 poziomach:

#### A) Position Monitor - ciągła reewaluacja
**Plik:** `bot/services/position_monitor.py`

```python
async def _save_reevaluation(
    self,
    pos: 'MonitoredPosition',
    reevaluation_type: str,  # 'trailing_sl', 'dynamic_sl', 'time_exit', etc.
    old_sl: Optional[float],
    new_sl: Optional[float],
    old_tp: Optional[float],
    new_tp: Optional[float],
    current_price: float,
    profit_pct: float,
    reason: str,
):
    """Log reevaluation to database."""
    if self._db_manager:
        try:
            with self._db_manager as db:
                db.save_reevaluation_log(
                    position_id=pos.symbol,
                    user_id=pos.user_id,
                    reevaluation_type=reevaluation_type,
                    old_stop_loss=old_sl,
                    new_stop_loss=new_sl,
                    old_take_profit=old_tp,
                    new_take_profit=new_tp,
                    current_price=current_price,
                    profit_percent=profit_pct,
                    reason=reason,
                )
        except Exception as e:
            logger.error(f"Failed to save reevaluation: {e}")
```

#### B) Signal Validator - walidacja przed wykonaniem
**Plik:** `bot/services/signal_validator.py`

```python
class SignalValidator:
    """
    Validates signals against historical data and current conditions.
    Adaptive confidence threshold based on market volatility.
    """
    
    def validate_signal(self, signal: Dict) -> ValidationResult:
        """
        Sprawdza:
        1. Czy sygnał jest świeży (< 2h)
        2. Czy confidence >= threshold
        3. Czy nie ma konfliktu z innymi sygnałami
        4. Czy wielkość pozycji jest rozsądna
        """
        
        # Adaptive threshold based on volatility
        if self.volatility_mode == 'high':
            threshold = 0.75  # Wyższy próg w wysokiej zmienności
        elif self.volatility_mode == 'low':
            threshold = 0.55  # Niższy próg w niskiej zmienności
        else:
            threshold = 0.65  # Standard
        
        if signal['confidence'] < threshold:
            return ValidationResult(valid=False, reason="Low confidence")
        
        return ValidationResult(valid=True)
```

#### C) Trading Cycle - reewaluacja co cykl
**Plik:** `bot/auto_trader.py` linia ~1600

```python
async def trading_cycle(self):
    # ... existing signals check ...
    
    # Reevaluate existing positions
    if self.position_monitor:
        for symbol, pos in self.position_monitor.positions.items():
            # Check if we should close early based on new analysis
            if ai_analysis:
                opposite_signal = [s for s in ai_analysis 
                                  if s['symbol'] == symbol 
                                  and s['action'] != pos.side]
                if opposite_signal and opposite_signal[0]['confidence'] > 0.8:
                    logger.info(f"🔄 High confidence reversal signal - closing {symbol}")
                    await self.position_monitor._execute_close(pos, "REVERSAL", current_price)
```

---

## 8. Jak działa logika wchodzenia w transakcje?

### 📊 Pełny flow wejścia w transakcję:

**Plik:** `bot/auto_trader.py` → `trading_cycle()`

```python
async def trading_cycle(self):
    """Main trading cycle - complete flow"""
    
    # ==== KROK 1: PRE-TRADE CHECKS ====
    
    # 1a. DCA Safety Order Check (NEW v4.0)
    if self.dca_manager and self.dca_enabled:
        executed = await self.dca_manager.check_and_execute_safety_orders()
    
    # 1b. Daily Loss Tracker Check
    if self.daily_loss_tracker:
        if not self.daily_loss_tracker.can_open_new_trade(self.user_id):
            return  # STOP - daily loss limit reached
    
    # 1c. Rate Limiter Check
    if self.rate_limiter:
        self.rate_limiter.start_cycle(self.user_id)
    
    # 1d. Kill Switch Check (extreme market conditions)
    if self.market_intelligence:
        should_kill, reason = await self.market_intelligence.should_kill_switch()
        if should_kill:
            logger.critical(f"🚨 KILL SWITCH: {reason}")
            return  # STOP - extreme conditions
    
    # ==== KROK 2: GET SIGNALS ====
    
    # 2a. Get signals from database
    db_signals = self.get_signals_from_database(quote_currency)
    
    # 2b. Deduplicate signals (prefer newest)
    if self.signal_deduplicator:
        dedup_result = self.signal_deduplicator.deduplicate_signals(
            user_id=self.user_id,
            signals=db_signals
        )
        db_signals = dedup_result.unique_signals
    
    # ==== KROK 3: VALIDATE SIGNALS ====
    
    # 3a. Check risk limits
    if not await self.check_risk_limits():
        return  # STOP - risk limits exceeded
    
    # 3b. Get market data
    market_data = await self.get_market_data()
    
    # 3c. Run AI analysis
    ai_analysis = await self.execute_ai_analysis(existing_market_data=market_data)
    
    # ==== KROK 4: EXECUTE TRADES ====
    
    # 4a. Run trading strategies
    signals = await self.trading_engine.run_cycle(external_market_data=market_data)
    
    # 4b. Filter signals with core modules
    filtered_signals = await self._filter_signals_with_core_modules(signals)
    
    # 4c. Execute each signal
    for signal in filtered_signals:
        await self._execute_signal(signal, market_data)
```

### Wykonanie pojedynczego sygnału:

```python
async def _execute_signal(self, signal: Dict, market_data: Dict):
    """Execute a single trading signal."""
    
    symbol = signal['symbol']
    action = signal['action']  # 'buy' or 'sell'
    
    # 1. Get position sizing
    size = await self._calculate_position_size(signal, market_data)
    
    # 2. Calculate SL/TP
    sl, tp = await self._calculate_sl_tp(signal, market_data)
    
    # 3. Check liquidity (v2.0)
    if self.market_intelligence:
        is_liquid = await self.market_intelligence.check_liquidity(symbol, size)
        if not is_liquid:
            logger.warning(f"⚠️ Insufficient liquidity for {symbol}")
            return
    
    # 4. Place order on exchange
    try:
        order = await self.exchange.place_order(
            symbol=symbol,
            side=action,
            order_type='market',
            quantity=size,
            stop_loss=sl,
            take_profit=tp,
            leverage=self.default_leverage
        )
        
        logger.info(f"✅ Order placed: {action} {size} {symbol} @ market")
        
    except Exception as e:
        logger.error(f"❌ Order failed: {e}")
        return
    
    # 5. Register with Position Monitor
    if self.position_monitor:
        await self.position_monitor.add_position(
            symbol=symbol,
            side='long' if action == 'buy' else 'short',
            entry_price=order['price'],
            quantity=size,
            stop_loss=sl,
            take_profit=tp,
            user_id=self.user_id
        )
    
    # 6. Save to database
    if self.db_manager:
        with self.db_manager as db:
            db.save_trade(
                user_id=self.user_id,
                symbol=symbol,
                trade_type=action,
                price=order['price'],
                amount=size,
                stop_loss=sl,
                take_profit=tp,
                leverage=self.default_leverage,
                source="auto_trader"
            )
    
    # 7. Update rate limiter
    if self.rate_limiter:
        self.rate_limiter.record_trade(self.user_id, symbol)
```

---

## 9. Gdzie bot zapisuje wykonane transakcje?

### 📍 Lokalizacje zapisu:

#### A) Tabela `trades` (główna)
**Plik:** `bot/db.py`

```python
def save_trade(
    self,
    *,
    user_id: str,           # UUID użytkownika
    symbol: str,            # np. 'BTC/USDT'
    trade_type: str,        # 'buy' lub 'sell'
    price: float,           # cena wykonania
    amount: float,          # ilość
    pnl: Optional[float],   # P&L (dla zamkniętych)
    source: str = "bot",    # 'bot', 'manual', 'position_monitor'
    exchange: str = "kraken",
    stop_loss: Optional[float],
    take_profit: Optional[float],
    leverage: Optional[float],
    entry_price: Optional[float],
    exit_price: Optional[float],
) -> Trade:
    """Save an executed trade to database."""
    trade = Trade(
        user_id=user_id,
        symbol=symbol,
        trade_type=trade_type.lower(),
        price=price,
        amount=amount,
        pnl=pnl,
        source=source,
        exchange=exchange,
        status="completed",
        stop_loss=stop_loss,
        take_profit=take_profit,
        leverage=leverage,
        entry_price=entry_price,
        exit_price=exit_price,
    )
    self.session.add(trade)
    self.session.flush()
    return trade
```

#### B) Tabela `positions` (dla otwartych)
```python
def create_position(
    self,
    symbol: str,
    side: str,
    quantity: float,
    entry_price: float,
    leverage: float,
    user_id: Optional[str],
    strategy: Optional[str],
    stop_loss: Optional[float],
    take_profit: Optional[float],
) -> Position:
    # Zapisuje otwartą pozycję
```

#### C) Tabela `trading_signals` (sygnały AI)
```python
def save_trading_signal(
    self,
    *,
    symbol: str,
    signal_type: str,       # 'buy', 'sell', 'hold'
    confidence_score: float,
    price_target: Optional[float],
    stop_loss: Optional[float],
    take_profit: Optional[float],
    entry_price: Optional[float],
    ai_analysis: Optional[str],
    source: str = "bot",
    user_id: Optional[str],
    status: str = "pending",
) -> TradingSignal:
```

#### D) Tabela `trading_stats` (statystyki dzienne)
```python
def record_trading_stats(
    self,
    *,
    date: datetime,
    starting_balance: float,
    ending_balance: float,
    realized_pnl: float,
    unrealized_pnl: float,
    trades: int,
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    max_drawdown: float,
    sharpe_ratio: Optional[float],
) -> TradingStats:
```

---

## 10. Dlaczego pliki testowe vs komercyjne?

### 📊 Wyjaśnienie struktury plików:

#### Pliki "testowe" to w rzeczywistości PRODUKCYJNE:

| Plik | Funkcja | Status |
|------|---------|--------|
| `auto_trader.py` | Główny trading bot | ✅ PRODUKCJA |
| `strategies.py` | Strategie tradingowe | ✅ PRODUKCJA |
| `risk_manager.py` | Zarządzanie ryzykiem | ✅ PRODUKCJA |
| `position_monitor.py` | Monitoring SL/TP | ✅ PRODUKCJA |
| `db.py` | Database models | ✅ PRODUKCJA |
| `ccxt_adapter.py` | Exchange adapter | ✅ PRODUKCJA |
| `run_multi_bots.py` | Multi-user launcher | ✅ PRODUKCJA |
| `monitor_group.py` | Group monitoring | ✅ PRODUKCJA |

#### Prawdziwe pliki testowe:

| Plik | Funkcja |
|------|---------|
| `tests/test_*.py` | Unit tests |
| `smoke_test.py` | Connection tests |
| `debug_*.py` | Debug utilities |
| `test_*.py` | Integration tests |

### ⚠️ Uwaga:
Nie używamy "plików testowych" zamiast komercyjnych. Wszystkie główne pliki (`auto_trader.py`, `strategies.py` itd.) są plikami produkcyjnymi używanymi w prawdziwym tradingu.

---

## 11. Luki techniczne, analityczne, logiczne

### 🔴 KRYTYCZNE (do naprawienia):

| # | Luka | Opis | Status |
|---|------|------|--------|
| K1 | Leverage-aware SL/TP | SL/TP nie uwzględniało leverage | ✅ NAPRAWIONE |
| K2 | Race conditions | Brak mutex na pozycjach | ✅ NAPRAWIONE (PositionLockManager) |
| K3 | Edge Function retry | Brak retry w Supabase Edge Functions | ✅ NAPRAWIONE |
| K4 | DCA brak | Brak Dollar Cost Averaging | ✅ NAPRAWIONE |

### 🟡 WAŻNE (do monitorowania):

| # | Luka | Opis | Wpływ |
|---|------|------|-------|
| W1 | WebSocket fallback | Fallback do REST może być wolny | Średni |
| W2 | Multi-exchange | Tylko Kraken/Binance | Średni |
| W3 | Correlation risk | Korelacja między pozycjami | Średni |

### 🟢 DROBNE (nice-to-have):

| # | Luka | Opis |
|---|------|------|
| D1 | UI dashboard | Brak real-time dashboard |
| D2 | Mobile app | Brak aplikacji mobilnej |
| D3 | Alerts | Podstawowe alerty email |

---

## 12. Porównanie z najlepszymi botami

### 📊 Feature Matrix:

| Feature | ASE Bot | 3Commas | Pionex | Cryptohopper |
|---------|---------|---------|--------|--------------|
| DCA | ✅ | ✅ | ✅ | ✅ |
| Grid Trading | ❌ | ✅ | ✅ | ✅ |
| AI Signals | ✅ | ❌ | ❌ | ✅ |
| Trailing SL | ✅ | ✅ | ✅ | ✅ |
| Dynamic SL/TP | ✅ | ❌ | ❌ | ❌ |
| Kelly Sizing | ✅ | ❌ | ❌ | ❌ |
| Partial TP | ✅ | ✅ | ❌ | ✅ |
| Time Exit | ✅ | ❌ | ❌ | ❌ |
| Kill Switch | ✅ | ❌ | ❌ | ✅ |
| Market Regime | ✅ | ❌ | ❌ | ❌ |
| Multi-Exchange | Partial | ✅ | Partial | ✅ |

### 🎯 Przewagi ASE Bot:
1. **AI-Driven Analysis** - zaawansowana analiza rynku
2. **Dynamic Risk Management** - ATR-based SL/TP
3. **Kelly Criterion** - matematycznie optymalne sizing
4. **Market Regime Detection** - dostosowanie do warunków
5. **Position Locking** - zapobieganie race conditions

### 📉 Do poprawy:
1. Grid trading
2. Więcej giełd
3. Lepsze UI

---

## 📝 Podsumowanie

ASE Bot to zaawansowany system tradingowy z:
- ✅ Pełnym zarządzaniem SL/TP (statyczne + dynamiczne + trailing)
- ✅ Position Monitor (monitoring co 5 sekund)
- ✅ Risk Manager (Kelly, ATR, Market Regime)
- ✅ DCA (Dollar Cost Averaging) - NOWE!
- ✅ Multi-user support
- ✅ Supabase persistence

**Status:** Produkcyjny, aktywnie rozwijany.
