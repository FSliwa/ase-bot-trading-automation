# 📊 COMPREHENSIVE SYSTEM ANALYSIS - ASE BOT v3.0

> **Dokument generowany:** 2025-01-15
> **Cel:** Pełna analiza mechanizmów tradingowych bota

---

## 📋 SPIS TREŚCI

1. [SL/TP i Dźwignia - Czy % uwzględnia leverage?](#1-sltp-i-dźwignia)
2. [Częstotliwość wykonywania transakcji](#2-częstotliwość-transakcji)
3. [Gdzie jest zapisywane SL/TP](#3-gdzie-jest-zapisywane-sltp)
4. [Jak działa śledzenie SL/TP](#4-śledzenie-sltp)
5. [Jak działa ustawianie dźwigni](#5-ustawianie-dźwigni)
6. [Jak działa ustawianie wielkości pozycji](#6-wielkość-pozycji)
7. [Sprawdzanie dostępnej waluty (USDT/USDC/USD)](#7-sprawdzanie-waluty)
8. [Logika reewaluacji transakcji](#8-logika-reewaluacji)
9. [Logika wchodzenia w transakcje](#9-logika-wchodzenia)
10. [Gdzie bot zapisuje transakcje w Supabase](#10-zapisywanie-transakcji)
11. [ZIDENTYFIKOWANE LUKI I PROBLEMY](#11-luki-i-problemy)

---

## 1. SL/TP i Dźwignia

### ❓ Pytanie: Czy TP i SL % ustawiony przez użytkownika uwzględnia dźwignię?

### ✅ ODPOWIEDŹ: **NIE** - SL/TP % są obliczane na bazie **ceny bazowej**, nie uwzględniają mnożnika dźwigni.

#### Jak to działa:

```python
# bot/services/position_monitor.py - linie 320-340
def _auto_set_sl_tp(self, side: str, entry_price: float, sl_percent, tp_percent):
    if side.lower() == 'long':
        stop_loss = entry_price * (1 - sl_pct / 100)    # Np. 100 * 0.95 = 95
        take_profit = entry_price * (1 + tp_pct / 100)  # Np. 100 * 1.03 = 103
    else:  # short
        stop_loss = entry_price * (1 + sl_pct / 100)
        take_profit = entry_price * (1 - tp_pct / 100)
```

#### ⚠️ PROBLEM:
Użytkownik ustawiający SL=5% z dźwignią 10x myśli, że straci 5% kapitału.
**ALE** faktycznie traci **5% × 10 = 50% kapitału** przy tej samej zmianie ceny!

#### Przykład:
| Parametr | Bez leverage | Z 10x leverage |
|----------|--------------|----------------|
| Entry Price | $100 | $100 |
| SL = 5% | SL @ $95 | SL @ $95 |
| Zmiana ceny do SL | -5% | -5% |
| **STRATA KAPITAŁU** | **-5%** | **-50%** |

#### 📍 Lokalizacja kodu:
- `bot/services/risk_manager.py` linie 510-570 - Dynamic SL/TP calculation
- `bot/services/position_monitor.py` linie 316-336 - Auto-set SL/TP

### 🔴 REKOMENDACJA:
Dodać opcję "leverage-aware SL/TP" która automatycznie dzieli % przez leverage:
```python
# Sugerowana poprawka:
effective_sl_pct = user_sl_pct / leverage  # 5% / 10 = 0.5% ruchu ceny
```

---

## 2. Częstotliwość Transakcji

### ❓ Pytanie: Jak często bot wykonuje transakcje?

### ✅ ODPOWIEDŹ: Bot używa **ADAPTIVE INTERVAL** - dynamicznie dostosowuje interwał.

#### Domyślne wartości (`auto_trader.py` linie 1750-1775):

| Warunek | Interwał |
|---------|----------|
| **Wysoka zmienność** (ATR > 4%) | 60s (1 min) |
| **Otwarte pozycje** | 180s (3 min) |
| **Bezczynność** (brak pozycji, normalne warunki) | 600s (10 min) |
| **Bazowy interwał** (TRADING_INTERVAL) | 300s (5 min) |

#### Position Monitor - Częstotliwość sprawdzania SL/TP:
```python
# bot/services/position_monitor.py linia 127
check_interval: float = 5.0  # Check every 5 seconds
```

#### Rate Limiter - Limity transakcji:
```python
# Domyślne limity (jeśli skonfigurowane):
max_trades_per_hour: 10
max_trades_per_day: 50
max_concurrent_positions: 5  # TradingConstants.MAX_CONCURRENT_TRADES
```

---

## 3. Gdzie jest zapisywane SL/TP

### ✅ ODPOWIEDŹ: W **TRZECH miejscach**:

### A) **Baza danych Supabase - tabela `trades`**
```python
# bot/db.py - Model Trade, linie 262-297
class Trade(Base):
    stop_loss = Column(Float, nullable=True)      # Stop loss price used
    take_profit = Column(Float, nullable=True)    # Take profit price used
    leverage = Column(Float, nullable=True)       # Leverage used
    entry_price = Column(Float, nullable=True)    # Original entry price
    exit_price = Column(Float, nullable=True)     # Actual exit price
```

### B) **Baza danych Supabase - tabela `positions`**
```python
# bot/db.py - Model Position, linie 50-95
class Position(Base):
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    leverage = Column(Float, nullable=False, default=1.0)
```

### C) **In-memory - PositionMonitor**
```python
# bot/services/position_monitor.py - MonitoredPosition dataclass
@dataclass
class MonitoredPosition:
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    original_stop_loss: Optional[float] = None  # Before trailing adjustment
    highest_price: Optional[float] = None  # For trailing long
    lowest_price: Optional[float] = None   # For trailing short
```

### D) **Tabela `trading_signals`** (źródło sygnałów)
```python
# bot/db.py - TradingSignal, linie 300-350
class TradingSignal(Base):
    stop_loss = Column(Numeric, nullable=True)
    take_profit = Column(Numeric, nullable=True)
    entry_price = Column(Numeric, nullable=True)
```

---

## 4. Śledzenie SL/TP

### ❓ Pytanie: Jak działa śledzenie SL i TP przez bota?

### ✅ ODPOWIEDŹ: **PositionMonitorService** sprawdza co **5 sekund**.

#### Mechanizm (`position_monitor.py` linie 500+):

```python
async def _monitor_loop(self):
    while self.running:
        for key, position in list(self.positions.items()):
            current_price = await self._get_current_price(position.symbol)
            
            # 1. Check SL/TP triggers
            triggered, trigger_type, trigger_price = self._check_triggers(position, current_price)
            
            # 2. Update trailing stop (if enabled)
            if position.trailing_enabled:
                self._update_trailing_stop(position, current_price)
            
            # 3. Check partial TP levels
            if self.enable_partial_tp:
                self._check_partial_tp(position, current_price)
            
            # 4. Check time-based exit
            if position.max_hold_hours:
                self._check_time_exit(position)
                
        await asyncio.sleep(self.check_interval)  # 5 seconds
```

#### Triggery SL/TP:

| Side | SL Trigger | TP Trigger |
|------|------------|------------|
| **LONG** | `current_price <= stop_loss` | `current_price >= take_profit` |
| **SHORT** | `current_price >= stop_loss` | `current_price <= take_profit` |

#### Trailing Stop Logic:
```python
# Aktywacja: gdy profit > activation_profit_percent (default 1.5%)
# Tiered trailing:
# - Profit 1.5%+: trailing 2%
# - Profit 3%+: trailing 1.5%
# - Profit 5%+: trailing 1%
# - Profit 7%+: trailing 0.75%
```

#### Partial Take Profit (domyślne poziomy):
```python
# Zamknij 40% pozycji przy +3% profit
# Zamknij 30% pozycji przy +5% profit  
# Zamknij 30% pozycji przy +7% profit
```

---

## 5. Ustawianie Dźwigni

### ❓ Pytanie: Jak działa ustawianie dźwigni?

### ✅ ODPOWIEDŹ: Zależy od **trybu i giełdy**.

#### Logika (`ccxt_adapter.py` linie 752-790):

```python
# L3 FIX: Proper leverage handling for SPOT vs FUTURES/MARGIN
is_spot_mode = not self.futures and not self.margin

if is_spot_mode:
    # SPOT MODE: Force leverage to 1 - no leverage supported
    if leverage and leverage > 1:
        logger.warning("SPOT does not support leverage. Using 1x.")
    actual_leverage = 1
    
elif leverage:  # FUTURES/MARGIN MODE
    if self.exchange.id == 'kraken':
        # Kraken: get best available leverage, pass in params
        actual_leverage = await self.get_best_leverage(symbol, leverage)
        params['leverage'] = actual_leverage
    elif self.exchange.id == 'binance':
        # Binance FUTURES: Set leverage via API
        actual_leverage = await self.set_leverage_safe(symbol, leverage)
```

#### Dostępne leverage na giełdach:

| Giełda | Spot | Margin | Futures |
|--------|------|--------|---------|
| **Kraken** | 1x | 2-5x | 2-50x |
| **Binance** | 1x | 3-10x | 1-125x |

#### ⚠️ UWAGA: Binance Spot **NIGDY** nie ma leverage!
Nawet jeśli użytkownik poprosi o 10x na Binance Spot, bot automatycznie ustawi 1x.

---

## 6. Wielkość Pozycji (Position Sizing)

### ❓ Pytanie: Jak działa ustawianie wielkości pozycji?

### ✅ ODPOWIEDŹ: **WIELOPOZIOMOWY SYSTEM** z kilkoma metodami.

#### Hierarchia metod (`risk_manager.py`):

### 6.1 **Kelly Criterion** (preferowana gdy wystarczająco danych)
```python
# Kelly Formula: f* = (bp - q) / b
# b = avg_win / avg_loss (win/loss ratio)
# p = win_rate (probability of winning)
# q = 1 - p

# Wymaga minimum 20 transakcji dla statystyk
# Progressive Kelly: zaczyna konserwatywnie (10% Kelly), 
# zwiększa do 25% przy 50+ transakcjach
```

### 6.2 **Volatility-Adjusted Sizing**
```python
# Position Size = (Capital × Risk%) / (Entry Price × SL Distance)
# 
# Volatility multipliers:
# - ATR > 4%: multiplier = 0.5 (very high volatility)
# - ATR > 3%: multiplier = 0.7
# - ATR > 2%: multiplier = 0.85
# - ATR < 1%: multiplier = 1.2 (can size up)
```

### 6.3 **Fixed Risk % per Trade**
```python
# Mapowanie risk_level -> risk_per_trade:
# Level 1 (Conservative): 0.25%
# Level 2 (Moderate):     0.50%
# Level 3 (Balanced):     1.00%
# Level 4 (Aggressive):   1.50%
# Level 5 (Very Aggressive): 2.00%
```

### 6.4 **User Settings Override**
```python
# UserRiskSettings (user-specific from DB):
@dataclass
class UserRiskSettings:
    risk_level: int = 3  # 1-5 scale
    max_position_size: float = 1000.0  # USD
    stop_loss_percentage: float = 5.0  # Default SL
    take_profit_percentage: float = 3.0  # Default TP
```

#### Caps (ograniczenia):
- `max_position_size_usd`: Default $1000 per position
- `MAX_CONCURRENT_TRADES`: 5 positions max
- Exchange minimums: bot automatycznie dostosowuje ilość do minimum giełdy

---

## 7. Sprawdzanie Dostępnej Waluty

### ❓ Pytanie: Jak działa sprawdzanie dostępnej waluty (USDT, USDC, USD)?

### ✅ ODPOWIEDŹ: **Kaskadowe sprawdzanie** z automatyczną konwersją.

#### Logika (`auto_trader.py` linie 1380-1420):

```python
async def manage_capital(self) -> str:
    # 1. Check USDT first
    usdt_balance = await self.exchange.get_specific_balance("USDT")
    if usdt_balance > 10:
        logger.info(f"Using USDT as quote currency (Balance: {usdt_balance:.2f})")
        return "USDT"

    # 2. Check USDC
    usdc_balance = await self.exchange.get_specific_balance("USDC")
    if usdc_balance > 10:
        logger.info(f"Using USDC as quote currency (Balance: {usdc_balance:.2f})")
        return "USDC"

    # 3. Check FIAT and auto-convert
    all_balances = await self.exchange.get_all_balances()
    fiat_currencies = ["USD", "EUR", "GBP", "PLN"]
    
    for currency, balance in all_balances.items():
        if currency in fiat_currencies and balance > 10:
            logger.info(f"Found FIAT: {balance:.2f} {currency}. Converting to USDC...")
            if await self.exchange.convert_currency(currency, "USDC", balance * 0.99):
                return "USDC"

    # 4. Fallback to USDT
    return "USDT"
```

#### get_specific_balance dla Binance Margin:
```python
# ccxt_adapter.py linie 192-208 (po fix)
async def get_specific_balance(self, currency: str) -> float:
    # Try spot balance first
    balance_info = await self.exchange.fetch_balance()
    free_balance = balance_info.get('free', {}).get(currency, 0)
    
    # If zero, try margin balance for Binance
    if free_balance == 0 and self.exchange.id == 'binance':
        try:
            margin_balance = await self.exchange.fetch_balance({'type': 'margin'})
            free_balance = margin_balance.get('free', {}).get(currency, 0)
        except:
            pass
    
    return float(free_balance or 0)
```

#### ⚠️ ZNANY PROBLEM: e4f7f9e4
Bot e4f7f9e4 ma 79 USDC na margin account ale `balance=0 USDT`.
Przyczyną może być:
1. Cross-margin vs Isolated-margin account type
2. `{'type': 'margin'}` nie pobiera isolated margin

---

## 8. Logika Reewaluacji

### ❓ Pytanie: Jak działa logika reewaluacji transakcji?

### ✅ ODPOWIEDŹ: **Wielowarstwowa walidacja** przed i w trakcie.

#### Pre-Trade Reevaluation:

```python
# auto_trader.py linie 1575-1650 - pre_trade_risk_check()
risk_check = await self.risk_manager_service.pre_trade_risk_check(
    symbol=symbol,
    signal_direction='long' if buy else 'short',
    position_size_usd=position_size,
    portfolio_value=portfolio_value,
    user_id=self.user_id
)

# Checks include:
# 1. VaR (Value at Risk) validation
# 2. Multi-timeframe alignment
# 3. Session timing (avoid low liquidity hours)
# 4. Sharpe ratio estimation
# 5. Correlation with existing positions
```

#### Signal Deduplication:
```python
# Usuwa duplikaty sygnałów dla tego samego symbolu
# Preferuje nowsze sygnały nad starszymi
# Filtruje sygnały starsze niż MAX_SIGNAL_AGE_SECONDS (300s = 5min)
```

#### AI Portfolio Evaluation (dla globalnych sygnałów):
```python
# Ocenia czy globalny sygnał pasuje do konkretnego użytkownika
evaluation = await evaluator.evaluate_signal_for_user(
    signal=sig,
    portfolio_state=portfolio_state
)
# Może odrzucić sygnał lub dostosować size multiplier
```

#### Dynamic SL/TP Adjustment:
```python
# RiskManager sprawdza okresowo czy SL/TP powinny być dostosowane
# Na podstawie aktualnego ATR i profilu zmienności
# SL może być tylko "zacieśniony" (moved in favor), nigdy poluzowany
```

---

## 9. Logika Wchodzenia w Transakcje

### ❓ Pytanie: Jak działa logika wchodzenia w transakcje?

### ✅ ODPOWIEDŹ: **Wieloetapowy pipeline**.

#### Pełny flow wejścia w transakcję:

```
1. ŹRÓDŁO SYGNAŁÓW
   │
   ├─► trading_signals table (PRIMARY)
   │   └─► titan_v3, manual signals, external feeds
   │
   └─► Edge Function FALLBACK (gdy brak sygnałów w DB)
       └─► COUNCIL V2.0 AI analysis
   
2. WALIDACJA SYGNAŁÓW
   │
   ├─► Signal age check (max 5 min)
   ├─► Duplicate check
   ├─► Exchange compatibility check
   └─► Confidence threshold (min 0.1 = 10%)
   
3. RISK CHECKS
   │
   ├─► Daily loss limit check
   ├─► Rate limiter check (trades/hour, trades/day)
   ├─► Market intelligence kill switch
   ├─► Correlation limit check
   └─► Pre-trade VaR check
   
4. PORTFOLIO EVALUATION
   │
   ├─► Available balance check
   ├─► Position count limit
   └─► AI evaluation (for global signals)
   
5. POSITION SIZING
   │
   ├─► Kelly Criterion (if enough data)
   ├─► Volatility adjustment
   └─► Risk % per trade
   
6. ORDER EXECUTION
   │
   ├─► Quantity adjustment to exchange minimums
   ├─► Leverage setting (if margin/futures)
   └─► SL/TP params (exchange-specific)
   
7. POST-TRADE
   │
   ├─► Save to Supabase trades table
   ├─► Add to Position Monitor
   └─► Update correlation manager
```

#### Strategie wbudowane (FALLBACK gdy brak AI sygnałów):

```python
# strategies.py
class MomentumStrategy:
    signal_threshold = 1.0  # 1% price change triggers signal
    
class MeanReversionStrategy:
    band_threshold = 2.0  # 2% bands around mid price
```

---

## 10. Zapisywanie Transakcji

### ❓ Pytanie: Gdzie bot zapisuje wykonane transakcje w Supabase?

### ✅ ODPOWIEDŹ: **Tabela `trades`** z pełnymi danymi.

#### Struktura tabeli `trades`:

```sql
-- PostgreSQL (Supabase)
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES profiles(id),
    exchange VARCHAR NOT NULL DEFAULT 'kraken',  -- enum: kraken, binance
    symbol VARCHAR NOT NULL,
    trade_type VARCHAR NOT NULL,  -- enum: buy, sell
    amount FLOAT NOT NULL,
    price FLOAT NOT NULL,
    fee FLOAT,
    fee_currency VARCHAR,
    status VARCHAR DEFAULT 'completed',  -- pending/completed/cancelled
    exchange_order_id VARCHAR,
    strategy_name VARCHAR,
    notes VARCHAR,
    executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    emotion VARCHAR,
    journal_notes VARCHAR,
    ai_insight VARCHAR,
    pnl FLOAT,
    source VARCHAR,  -- bot/manual/position_monitor
    
    -- L2 FIX v3.0: New fields
    stop_loss FLOAT,
    take_profit FLOAT,
    leverage FLOAT,
    entry_price FLOAT,
    exit_price FLOAT
);
```

#### Miejsca zapisywania:

| Callback | Źródło | Dane |
|----------|--------|------|
| `_on_sl_triggered()` | PositionMonitor | SL hit, PnL, exit_price |
| `_on_tp_triggered()` | PositionMonitor | TP hit, PnL, exit_price |
| `_on_partial_tp_triggered()` | PositionMonitor | Partial close |
| `_on_time_exit_triggered()` | PositionMonitor | Time-based exit |
| `_save_trade_to_db()` | TradingEngine | Manual/strategy trades |

#### Kod zapisu (`db.py` linie 1040-1090):
```python
def save_trade(
    self,
    *,
    user_id: str,
    symbol: str,
    trade_type: str,  # 'buy' or 'sell'
    price: float,
    amount: float,
    pnl: Optional[float] = None,
    source: str = "bot",
    emotion: Optional[str] = None,
    exchange: str = "kraken",
    # L2 FIX v3.0:
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    leverage: Optional[float] = None,
    entry_price: Optional[float] = None,
    exit_price: Optional[float] = None,
) -> Trade:
    trade = Trade(
        user_id=user_id,
        symbol=symbol,
        trade_type=trade_type.lower(),
        price=price,
        amount=amount,
        pnl=pnl,
        source=source,
        emotion=emotion,
        exchange=exchange.lower(),
        status="completed",
        stop_loss=stop_loss,
        take_profit=take_profit,
        leverage=leverage,
        entry_price=entry_price,
        exit_price=exit_price,
    )
    self.session.add(trade)
    return trade
```

---

## 11. ZIDENTYFIKOWANE LUKI I PROBLEMY

### 🔴 KRYTYCZNE

| # | Problem | Lokalizacja | Wpływ | Status |
|---|---------|-------------|-------|--------|
| **K1** | SL/TP % nie uwzględnia dźwigni | position_monitor.py | Użytkownik może stracić 50% kapitału myśląc że 5% | ✅ **NAPRAWIONE** |
| **K2** | titan_v3 zwraca HOLD/0% | External service | Brak sygnałów = brak transakcji | ⚠️ Zewnętrzne |
| **K3** | Edge Function empty response | supabase_analysis_service.py | Brak fallback AI sygnałów | ✅ **NAPRAWIONE** |
| **K4** | e4f7f9e4 margin balance = 0 | ccxt_adapter.py | 79 USDC niewidoczne | ⏳ Do zbadania |

### ✅ K1 FIX - Leverage-Aware SL/TP

**Zmienione pliki:**
- `bot/services/position_monitor.py`

**Co naprawiono:**
1. Dodano pole `leverage` i `leverage_aware_sl_tp` do `MonitoredPosition` dataclass
2. Funkcja `_auto_set_sl_tp()` teraz przelicza % na podstawie leverage
3. Z 5% SL i 10x leverage → actual price SL = 0.5% (chroni 5% kapitału)

**Przykład:**
```python
# Przed (błędne):
SL = entry_price * (1 - 5/100)  # 5% price move = 50% capital loss with 10x

# Po (poprawione):
effective_sl = 5% / 10x = 0.5%
SL = entry_price * (1 - 0.5/100)  # 0.5% price move = 5% capital loss
```

### ✅ K3 FIX - Edge Function Enhanced

**Zmienione pliki:**
- `bot/services/supabase_analysis_service.py`

**Co naprawiono:**
1. Timeout zwiększony: 60s → **90s**
2. Retries zwiększone: 3 → **4** z exponential backoff
3. Dodano obsługę różnych formatów odpowiedzi (signals, data, results)
4. Szczegółowe logowanie pustych odpowiedzi z możliwymi przyczynami
5. Obsługa różnych nazw pól (symbol/coin/asset, action/signal/recommendation)
6. Poprawiona konstrukcja URL (unika duplikacji /functions/v1)

### 🟠 WYSOKIE

| # | Problem | Lokalizacja | Wpływ |
|---|---------|-------------|-------|
| **W1** | Brak leverage w user_settings UI | Frontend | Użytkownik nie może ustawić preferowanego leverage |
| **W2** | Kelly needs 20 trades minimum | risk_manager.py | Nowi użytkownicy używają fixed % |
| **W3** | No SL/TP on Binance Spot orders | ccxt_adapter.py | SL/TP tylko przez Position Monitor (software stop) |
| **W4** | Position Monitor in-memory | position_monitor.py | Restart bota = utrata monitoringu |

### 🟡 ŚREDNIE

| # | Problem | Lokalizacja | Wpływ |
|---|---------|-------------|-------|
| **S1** | EXCHANGE_NAME filter (naprawione) | auto_trader.py | Było blokowane dla Binance |
| **S2** | MomentumStrategy threshold 1% | strategies.py | Może generować dużo sygnałów w zmiennym rynku |
| **S3** | No SMS/Push alerts for SL/TP | - | Użytkownik nie wie gdy pozycja zamknięta |
| **S4** | Trailing stop starts at 1.5% | risk_manager.py | Może być za mało dla volatile assets |

### 🟢 NISKIE / SUGESTIE

| # | Sugestia | Lokalizacja |
|---|----------|-------------|
| **N1** | Dodać "effective SL/TP after leverage" w UI | Frontend |
| **N2** | Sync Position Monitor state do DB | position_monitor.py |
| **N3** | Webhook notifications dla SL/TP triggers | auto_trader.py |
| **N4** | Edge Function timeout increase 60s → 90s | supabase_analysis_service.py |

---

## 📊 PODSUMOWANIE ARCHITEKTURY

```
┌────────────────────────────────────────────────────────────────────┐
│                        ASE BOT v3.0 ARCHITECTURE                   │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌─────────────┐     ┌──────────────┐     ┌──────────────────┐    │
│  │ SIGNAL      │────►│ VALIDATION   │────►│ RISK MANAGEMENT  │    │
│  │ SOURCES     │     │ LAYER        │     │                  │    │
│  │             │     │              │     │ • Daily Loss     │    │
│  │ • titan_v3  │     │ • Age check  │     │ • Rate Limiter   │    │
│  │ • Edge Fn   │     │ • Dedup      │     │ • VaR Check      │    │
│  │ • Built-in  │     │ • Confidence │     │ • Correlation    │    │
│  └─────────────┘     └──────────────┘     └────────┬─────────┘    │
│                                                     │              │
│                                                     ▼              │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    POSITION SIZING                           │  │
│  │                                                              │  │
│  │  Kelly Criterion → Volatility Adjust → Fixed Risk % → Caps  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                     │              │
│                                                     ▼              │
│  ┌─────────────┐     ┌──────────────┐     ┌──────────────────┐    │
│  │ ORDER       │────►│ EXCHANGE     │────►│ POSITION         │    │
│  │ EXECUTION   │     │ ADAPTER      │     │ MONITOR          │    │
│  │             │     │              │     │                  │    │
│  │ • Qty adj   │     │ • Kraken     │     │ • SL/TP Track    │    │
│  │ • Leverage  │     │ • Binance    │     │ • Trailing Stop  │    │
│  │ • SL/TP     │     │ • Others     │     │ • Partial TP     │    │
│  └─────────────┘     └──────────────┘     └────────┬─────────┘    │
│                                                     │              │
│                                                     ▼              │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    SUPABASE DATABASE                         │  │
│  │                                                              │  │
│  │  positions │ trades │ trading_signals │ profiles │ api_keys │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 📝 NASTĘPNE KROKI

1. **K1 FIX**: Dodać leverage-aware SL/TP calculation
2. **K3 FIX**: Debug Edge Function empty response
3. **K4 FIX**: Fix Binance margin balance detection dla isolated margin
4. **W3 IMPROVE**: Zbadać czy Binance Spot ma conditional orders (OCO)
5. **W4 FIX**: Persist Position Monitor state to database

---

*Dokument wygenerowany przez GitHub Copilot na podstawie analizy kodu ASE BOT v3.0*
