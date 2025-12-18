# 🔍 KOMPLEKSOWA ANALIZA SYSTEMU ASE BOT v3.0

**Data analizy:** 13 grudnia 2025  
**Autor:** AI Code Analyst

---

## 📋 SPIS TREŚCI

1. [Gdzie zapisywane są SL/TP](#1-gdzie-zapisywane-są-sltp)
2. [Jak działa śledzenie SL/TP przez bota](#2-jak-działa-śledzenie-sltp-przez-bota)
3. [Jak działa ustawianie dźwigni](#3-jak-działa-ustawianie-dźwigni)
4. [Jak działa ustawianie wielkości pozycji](#4-jak-działa-ustawianie-wielkości-pozycji)
5. [Jak działa ustawianie SL/TP](#5-jak-działa-ustawianie-sltp)
6. [Jak działa sprawdzanie dostępnej waluty](#6-jak-działa-sprawdzanie-dostępnej-waluty)
7. [Jak działa logika reewaluacji transakcji](#7-jak-działa-logika-reewaluacji-transakcji)
8. [Jak działa logika wchodzenia w transakcje](#8-jak-działa-logika-wchodzenia-w-transakcje)
9. [Gdzie bot zapisuje wykonane transakcje w Supabase](#9-gdzie-bot-zapisuje-wykonane-transakcje-w-supabase)
10. [**WYKRYTE LUKI I PROBLEMY**](#10-wykryte-luki-i-problemy)

---

## 1. GDZIE ZAPISYWANE SĄ SL/TP

### 📁 Lokalizacje przechowywania SL/TP:

| Lokalizacja | Plik | Opis |
|-------------|------|------|
| **Signal dataclass** | `bot/strategies.py:73-74` | `stop_loss`, `take_profit` jako Optional[float] |
| **MonitoredPosition** | `bot/services/position_monitor.py:50-51` | W pamięci RAM dla monitoringu |
| **Position DB model** | `bot/db.py` | Tabela `positions` w Supabase |
| **TradingSignal DB** | Supabase | Tabela `trading_signals` |

### Kod źródłowy:
```python
# bot/strategies.py - Signal dataclass
@dataclass
class Signal:
    stop_loss: Optional[float] = None      # Linia 73
    take_profit: Optional[float] = None    # Linia 74
    leverage: Optional[float] = 10.0       # Linia 75
```

```python
# bot/services/position_monitor.py - MonitoredPosition
@dataclass
class MonitoredPosition:
    stop_loss: Optional[float] = None      # Linia 50
    take_profit: Optional[float] = None    # Linia 51
    trailing_enabled: bool = False         # Trailing stop
    highest_price: Optional[float] = None  # Dla long
    lowest_price: Optional[float] = None   # Dla short
```

### ⚠️ LUKA #1: SL/TP nie jest zapisywane w tabeli `trades`
- Transakcje są zapisywane w `save_trade()` bez SL/TP
- Brak historii SL/TP dla audytu

---

## 2. JAK DZIAŁA ŚLEDZENIE SL/TP PRZEZ BOTA

### 📊 Architektura monitoringu:

```
┌─────────────────────────────────────────────────────────────┐
│                  POSITION MONITOR SERVICE                    │
│                  (bot/services/position_monitor.py)          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │ CHECK SL/TP │───▶│ TRAILING SL │───▶│ TIME EXIT   │      │
│  │ (5s loop)   │    │ (dynamic)   │    │ (12h max)   │      │
│  └─────────────┘    └─────────────┘    └─────────────┘      │
│         │                  │                  │              │
│         ▼                  ▼                  ▼              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │ PARTIAL TP  │    │ DYNAMIC SL  │    │ ALERTS      │      │
│  │ (3%,5%,7%)  │    │ (volatility)│    │ (email)     │      │
│  └─────────────┘    └─────────────┘    └─────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### Proces monitoringu (linia 720-880):
1. **Pętla główna** - `_monitor_loop()` - co 5 sekund
2. **Sprawdzenie wszystkich pozycji** - `_check_all_positions()`
3. **Sprawdzenie TIME EXIT** - Auto-zamknięcie po X godzinach
4. **Sprawdzenie PARTIAL TP** - Skalowanie wyjścia
5. **TRAILING STOP** - Dynamiczne przesuwanie SL
6. **DYNAMIC SL/TP** - Dostosowanie do volatility (co 60s)
7. **CHECK SL** - Porównanie ceny z SL
8. **CHECK TP** - Porównanie ceny z TP

### Logika sprawdzania SL (linia 840-858):
```python
if pos.side == 'long' and current_price <= pos.stop_loss:
    sl_triggered = True
elif pos.side == 'short' and current_price >= pos.stop_loss:
    sl_triggered = True
```

### Logika sprawdzania TP (linia 860-875):
```python
if pos.side == 'long' and current_price >= pos.take_profit:
    tp_triggered = True
elif pos.side == 'short' and current_price <= pos.take_profit:
    tp_triggered = True
```

### ⚠️ LUKA #2: Pozycje na giełdzie mogą nie mieć SL/TP
- Binance SPOT nie obsługuje SL/TP w jednym zleceniu
- Bot monitoruje software'owo, ale nie stawia zleceń SL/TP na giełdzie
- W przypadku awarii bota, pozycje są niechronione!

---

## 3. JAK DZIAŁA USTAWIANIE DŹWIGNI

### 📊 Flow ustawiania dźwigni:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Signal     │────▶│  LiveBroker  │────▶│ CCXTAdapter  │
│ leverage=10  │     │ place_order  │     │ place_order  │
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                     ┌───────────────────────────┘
                     ▼
         ┌─────────────────────────────────────────┐
         │ Exchange-specific leverage handling:     │
         │                                         │
         │ KRAKEN:   get_best_leverage(symbol, 10) │
         │           params['leverage'] = actual   │
         │                                         │
         │ BINANCE:  Spot = NO LEVERAGE            │
         │           Futures = set_leverage_safe() │
         │                                         │
         │ OTHER:    set_leverage_safe() fallback  │
         └─────────────────────────────────────────┘
```

### Kod źródłowy (ccxt_adapter.py:712-727):
```python
if leverage and self.futures:
    if self.exchange.id == 'kraken':
        # Kraken: get best available leverage and pass in params
        actual_leverage = await self.get_best_leverage(symbol, leverage)
        params['leverage'] = actual_leverage
    elif self.exchange.id == 'binance':
        # Binance SPOT: No leverage, skip
        # Binance FUTURES: Set leverage via API
        if self.futures:
            actual_leverage = await self.set_leverage_safe(symbol, leverage)
    else:
        # Other exchanges: try to set leverage with fallback
        actual_leverage = await self.set_leverage_safe(symbol, leverage)
```

### ⚠️ LUKA #3: Dźwignia jest IGNOROWANA na Binance SPOT
- Kod ustawia `leverage=10.0` ale Binance Spot nie obsługuje dźwigni
- Pozycja spot jest 1:1, ale system może źle kalkulować PnL

---

## 4. JAK DZIAŁA USTAWIANIE WIELKOŚCI POZYCJI

### 📊 Hierarchia kalkulacji rozmiaru:

```
┌───────────────────────────────────────────────────────────┐
│            POSITION SIZING PIPELINE                        │
├───────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │ 1. KELLY    │    │ 2. VOLATILITY│   │ 3. COMBINED │    │
│  │ CRITERION   │───▶│ ADJUSTED     │──▶│ OPTIMAL     │    │
│  └─────────────┘    └─────────────┘    └─────────────┘    │
│        │                  │                  │             │
│        └──────────────────┼──────────────────┘             │
│                           ▼                                │
│           ┌─────────────────────────────────┐             │
│           │ min(kelly_size, vol_size)        │             │
│           │ × confidence_multiplier          │             │
│           │ capped at max_position_size      │             │
│           │ validated vs exchange minimums   │             │
│           └─────────────────────────────────┘             │
└───────────────────────────────────────────────────────────┘
```

### Kod źródłowy (risk_manager.py:1034-1105):
```python
async def calculate_optimal_position_size(
    self,
    symbol: str,
    capital: float,
    current_price: float,
    confidence: float = 0.5,
    user_id: Optional[str] = None
) -> PositionSizeResult:
    """
    Strategy:
    1. Get Kelly size (based on historical performance)
    2. Get Volatility-adjusted size (based on market conditions)
    3. Take the smaller of the two (conservative approach)
    4. Adjust by signal confidence
    5. Cap at user's max_position_size
    6. Validate against exchange minimums
    """
```

### Parametry użytkownika:
- `max_position_size` - domyślnie $1000
- `risk_per_trade` - % kapitału na trade
- `stop_loss_percentage` - domyślny SL %
- `take_profit_percentage` - domyślny TP %

### ⚠️ LUKA #4: Brak walidacji minimalnych wartości dla każdej giełdy
- Niektóre giełdy wymagają min. $10, inne $1
- Bot może próbować postawić zbyt małe zlecenie

---

## 5. JAK DZIAŁA USTAWIANIE SL/TP

### 📊 Źródła SL/TP:

| Źródło | Priorytet | Opis |
|--------|-----------|------|
| **Sygnał AI** | 1 (najwyższy) | `analysis.get('stop_loss')`, `analysis.get('take_profit')` |
| **Sygnał z DB** | 2 | `signal.stop_loss`, `signal.take_profit` z trading_signals |
| **Targets (AI)** | 3 | `analysis.get('targets')[0]` jako TP |
| **Auto-set** | 4 (fallback) | Domyślne % z ustawień użytkownika |

### Kod źródłowy (strategies.py:349-361):
```python
# Add take profit - check both 'take_profit' (from DB) and 'targets' (from AI)
take_profit_price = analysis.get('take_profit')
if take_profit_price:
    signal.take_profit = float(take_profit_price)
elif analysis.get('targets'):
    targets = analysis.get('targets')
    if targets and len(targets) > 0:
        signal.take_profit = float(targets[0])

stop_loss_price = analysis.get('stop_loss')
if stop_loss_price:
    signal.stop_loss = float(stop_loss_price)
```

### Auto-set SL/TP (position_monitor.py):
```python
DEFAULT_SL_PERCENT = 5.0   # 5% stop loss
DEFAULT_TP_PERCENT = 7.0   # 7% take profit
DEFAULT_MAX_HOLD_HOURS = 12.0  # 12h max hold
```

### ⚠️ LUKA #5: SL/TP dla spot trading jest tylko software'owe
- Binance SPOT nie obsługuje SL/TP w parametrach zlecenia
- Kod loguje: `"SL/TP not in order params, will be managed by Position Monitor"`
- Jeśli bot padnie, pozycja jest niechroniona!

---

## 6. JAK DZIAŁA SPRAWDZANIE DOSTĘPNEJ WALUTY

### 📊 Obsługiwane waluty:

| Waluta | Priorytet | Giełda |
|--------|-----------|--------|
| USDT | 1 | Wszystkie |
| USDC | 2 | Wszystkie |
| USD | 3 | Kraken |
| EUR | 4 | Kraken |
| ZUSD | 5 | Kraken (natywna nazwa) |
| ZEUR | 6 | Kraken (natywna nazwa) |
| BUSD | 7 | Binance (deprecated) |

### Kod źródłowy (live_broker.py:75-119):
```python
async def get_balance(self) -> Dict:
    balance = await self.client.exchange.fetch_balance()
    
    quote_currencies = ['USDT', 'USDC', 'USD', 'EUR', 'ZUSD', 'ZEUR']
    
    # Find best available quote currency
    available_balance = 0
    used_currency = 'USDT'  # default
    
    for currency in quote_currencies:
        bal = balance.get(currency, {})
        if isinstance(bal, dict):
            free = float(bal.get('free', 0) or 0)
        else:
            free = float(bal or 0)
        if free > available_balance:
            available_balance = free
            used_currency = currency
```

### Kod źródłowy (ccxt_adapter.py:280-290):
```python
# Sum up USDT/USDC as margin proxy
free_margin = float(free.get('USDT', 0) or 0) + float(free.get('USDC', 0) or 0)
used_margin = float(used.get('USDT', 0) or 0) + float(used.get('USDC', 0) or 0)
```

### ⚠️ LUKA #6: Brak automatycznej konwersji walut
- Jeśli użytkownik ma EUR, a para to BTC/USDT - nie może handlować
- Brak sugestii do wymiany waluty

---

## 7. JAK DZIAŁA LOGIKA REEWALUACJI TRANSAKCJI

### 📊 Typy reewaluacji:

| Typ | Trigger | Akcja |
|-----|---------|-------|
| **trailing_update** | Nowy szczyt ceny | Przesunięcie SL w górę |
| **dynamic_sl_update** | Zmiana volatility | Dostosowanie SL do ATR |
| **sl_triggered** | Cena <= SL | Zamknięcie pozycji |
| **tp_triggered** | Cena >= TP | Zamknięcie pozycji |
| **time_exit** | Hold > max_hours | Zamknięcie jeśli profitable |
| **partial_tp** | Profit >= level% | Częściowe zamknięcie |

### Trailing Stop Logic (position_monitor.py:1050-1120):
```python
async def _apply_trailing_stop(self, key: str, pos: MonitoredPosition, current_price: float):
    # For LONG: track highest price, move SL up
    if pos.side == 'long':
        if pos.highest_price is None or current_price > pos.highest_price:
            pos.highest_price = current_price
        
        # Calculate new trailing SL
        new_sl = pos.highest_price * (1 - pos.trailing_distance_percent / 100)
        
        # Only move SL up, never down
        if new_sl > pos.stop_loss:
            old_sl = pos.stop_loss
            pos.stop_loss = new_sl
            pos.trailing_activated = True
```

### Time Exit Logic (position_monitor.py:880-930):
```python
async def _check_time_exit(self, key: str, pos: MonitoredPosition, current_price: float):
    hold_hours = (datetime.now() - pos.opened_at).total_seconds() / 3600
    
    if hold_hours >= pos.max_hold_hours:
        # FIX 2025-12-13: Only close if profitable OR exceeded 2x max_hold
        is_profitable = pnl_percent > 0
        is_force_close = hold_hours >= pos.max_hold_hours * 2
        
        if is_profitable or is_force_close:
            await self._handle_time_exit(key, pos, current_price)
            return True
```

### Zapis reewaluacji do DB:
```python
INSERT INTO position_reevaluations 
(position_id, user_id, symbol, reevaluation_type, 
old_sl, new_sl, old_tp, new_tp, current_price, profit_pct, reason, action_taken)
VALUES (...)
```

---

## 8. JAK DZIAŁA LOGIKA WCHODZENIA W TRANSAKCJE

### 📊 Pipeline wejścia w transakcję:

```
┌────────────────────────────────────────────────────────────────────────┐
│                    TRADE ENTRY PIPELINE                                 │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  1. SIGNAL ACQUISITION                                                 │
│     ├── Database signals (TRUSTED_SOURCES)                            │
│     └── Edge Function fallback                                        │
│                                                                        │
│  2. AI EVALUATION (SignalValidator)                                   │
│     ├── Confidence score                                              │
│     ├── should_execute flag                                           │
│     └── position_size_multiplier                                      │
│                                                                        │
│  3. PRE-TRADE RISK CHECK                                              │
│     ├── VaR (Value at Risk)                                           │
│     ├── Multi-timeframe analysis                                      │
│     ├── Session timing                                                │
│     ├── Sharpe ratio                                                  │
│     └── Correlation check                                             │
│                                                                        │
│  4. POSITION SIZING                                                   │
│     ├── Kelly Criterion                                               │
│     ├── Volatility adjustment                                         │
│     └── Exchange minimum validation                                   │
│                                                                        │
│  5. ORDER EXECUTION                                                   │
│     ├── Symbol normalization                                          │
│     ├── Leverage setting (if supported)                               │
│     ├── Order placement                                               │
│     └── Position Monitor registration                                 │
│                                                                        │
│  6. POST-TRADE                                                        │
│     ├── Save trade to DB                                              │
│     ├── Update positions                                              │
│     └── Log to daily_loss_tracker                                     │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Główny kod (auto_trader.py:1550-1630):
```python
# 1. Check correlation limit
if self.correlation_manager:
    can_add, reason = self.correlation_manager.check_correlation_limit(...)
    if not can_add:
        logger.warning(f"Signal blocked by correlation manager: {reason}")
        continue

# 2. Pre-trade risk check
risk_check = await self.risk_manager_service.pre_trade_risk_check(...)
if not risk_check['can_trade']:
    logger.warning(f"Signal blocked by pre-trade risk check")
    continue

# 3. Apply size adjustment
if risk_check['size_multiplier'] < 1.0:
    signal.quantity *= risk_check['size_multiplier']
```

### Warunki blokujące wejście:
- `can_trade = False` - margin level < 150%
- Correlation limit exceeded
- VaR limit exceeded
- Daily loss limit reached
- Session timing (off-hours)

---

## 9. GDZIE BOT ZAPISUJE WYKONANE TRANSAKCJE W SUPABASE

### 📁 Tabele w Supabase:

| Tabela | Opis | Zapisywane przez |
|--------|------|------------------|
| `trades` | Historia transakcji | `db.save_trade()` |
| `positions` | Otwarte pozycje | `live_broker`, `strategies` |
| `trading_signals` | Sygnały | `auto_trader.py` |
| `position_reevaluations` | Historia zmian SL/TP | `position_monitor` |

### Kod źródłowy (db.py:1033-1062):
```python
def save_trade(
    self,
    *,
    user_id: str,
    symbol: str,
    trade_type: str,     # 'buy', 'sell', 'close'
    price: float,
    amount: float,
    pnl: Optional[float] = None,
    source: str = "bot",
    emotion: Optional[str] = None,
    exchange: str = "kraken",
) -> Trade:
    """Save an executed trade to the database."""
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
    )
    self.session.add(trade)
    self.session.flush()
    return trade
```

### Miejsca wywołania save_trade():
1. `strategies.py:528` - `_save_trade_to_db()` - po BUY/SELL/CLOSE
2. `auto_trader.py:1791` - po SL trigger
3. `auto_trader.py:1832` - po TP trigger
4. `auto_trader.py:1853` - po Time Exit
5. `auto_trader.py:1883` - po Partial TP

### ⚠️ LUKA #7: Brak pełnych danych w tabeli `trades`
Zapisywane pola:
- ✅ user_id, symbol, trade_type, price, amount, pnl, source, exchange
- ❌ **BRAK**: stop_loss, take_profit, leverage, entry_price, exit_price, commission

---

## 10. WYKRYTE LUKI I PROBLEMY

### ✅ NAPRAWIONE (13 grudnia 2025)

| # | Problem | Status | Rozwiązanie |
|---|---------|--------|-------------|
| **L1** | SL/TP tylko software'owe dla Spot | ✅ NAPRAWIONE | Dodano `place_order_with_oco()` - OCO orders dla Binance SPOT |
| **L3** | Dźwignia ignorowana na Spot | ✅ NAPRAWIONE | Dodano walidację `is_spot_mode` - wymusza leverage=1 dla SPOT |
| **L4** | Brak konwersji walut | ✅ NAPRAWIONE | Dodano `find_best_trading_pair()` i `suggest_currency_conversion()` |
| **L5** | Brak walidacji minimów | ✅ JUŻ BYŁO | `get_min_order_amount()` i `adjust_quantity_to_minimum()` |

### Szczegóły napraw:

#### L1 - OCO Orders dla Binance SPOT
**Plik:** `bot/http/ccxt_adapter.py`
**Nowa metoda:** `place_order_with_oco()`
- Po głównym zleceniu tworzy OCO order z SL i TP
- Automatyczne anulowanie jednego przy trigger drugiego
- Hardware protection - chroni pozycję nawet gdy bot nie działa

#### L3 - Dźwignia na SPOT
**Plik:** `bot/http/ccxt_adapter.py` 
**Zmiana w:** `place_order()`
```python
is_spot_mode = not self.futures and not self.margin
if is_spot_mode:
    # SPOT MODE: Force leverage to 1
    actual_leverage = 1
```

#### L4 - Konwersja walut
**Plik:** `bot/http/ccxt_adapter.py`
**Nowe metody:**
- `find_best_trading_pair()` - szuka alternatywnej pary
- `suggest_currency_conversion()` - sugeruje konwersję waluty
- `get_tradeable_balance_for_symbol()` - sprawdza czy user może tradować

**Plik:** `bot/broker/live_broker.py`
- Automatyczne sprawdzanie przed zleceniem
- Zwraca `alternative_pair` jeśli nie może tradować głównej pary

---

### 🟠 POZOSTAŁE DO NAPRAWY

| # | Problem | Lokalizacja | Wpływ | Rozwiązanie |
|---|---------|-------------|-------|-------------|
| **L2** | **Brak SL/TP w tabeli trades** | db.py:1033 | Brak historii dla audytu | Dodanie kolumn sl, tp, leverage |
| **L6** | **Rate limiter na Kraken** | logi botów | Rate limit exceeded | Implementacja exponential backoff |

### 🟡 ŚREDNIE (P2)

| # | Problem | Lokalizacja | Wpływ | Rozwiązanie |
|---|---------|-------------|-------|-------------|
| **L7** | **Brak entry_price/exit_price w trades** | db.py | Niekompletny audyt | Dodanie kolumn |
| **L8** | **Margin level warning** | ccxt_adapter.py:259 | Niejasna informacja dla użytkownika | Lepszy komunikat |
| **L9** | **Ghost positions** | position_monitor.py:600 | Pozycje w DB nie na giełdzie | Regularna reconciliacja |

### 🟢 NISKIE (P3)

| # | Problem | Lokalizacja | Wpływ | Rozwiązanie |
|---|---------|-------------|-------|-------------|
| **L10** | **Hardcoded symbols** | strategies.py:393 | Ograniczona lista par | Dynamiczne pobieranie |
| **L11** | **Brak commission tracking** | db.py | Niepełna kalkulacja PnL | Dodanie kolumny commission |

---

## 📝 REKOMENDACJE PRIORYTETOWE

### Pozostałe do implementacji:

1. **� L2** - Rozszerzyć tabele `trades`:
```sql
ALTER TABLE trades ADD COLUMN stop_loss DECIMAL(20,8);
ALTER TABLE trades ADD COLUMN take_profit DECIMAL(20,8);
ALTER TABLE trades ADD COLUMN leverage DECIMAL(5,2);
ALTER TABLE trades ADD COLUMN entry_price DECIMAL(20,8);
ALTER TABLE trades ADD COLUMN exit_price DECIMAL(20,8);
ALTER TABLE trades ADD COLUMN commission DECIMAL(20,8);
```

---

## 📊 PODSUMOWANIE PO NAPRAWACH (13.12.2025)

| Kategoria | Status | Szczegóły |
|-----------|--------|-----------|
| **Zapisywanie SL/TP** | ⚠️ Częściowe | W pamięci + monitor, brak w trades DB |
| **Śledzenie SL/TP** | ✅ Działa | Position Monitor co 5s + OCO orders (L1 FIX) |
| **Ustawianie dźwigni** | ✅ NAPRAWIONE | L3 FIX: Walidacja SPOT vs FUTURES/MARGIN |
| **Wielkość pozycji** | ✅ Zaawansowane | Kelly + Volatility + Minimums validation (L5) |
| **Dostępna waluta** | ✅ NAPRAWIONE | L4 FIX: Auto-find trading pair + conversion suggestion |
| **Reewaluacja** | ✅ Kompletna | Trailing, Dynamic SL, Time Exit, zapisywane |
| **Wchodzenie w transakcje** | ✅ Zaawansowane | Multi-check pipeline + currency validation |
| **Zapis do Supabase** | ⚠️ Niekompletny | trades, positions, signals - brak pełnych danych |

**Ogólna ocena systemu po naprawach: 8.5/10** ⬆️ (+1.0)
- ✅ OCO orders dla Binance SPOT - hardware protection
- ✅ Prawidłowa obsługa dźwigni SPOT/FUTURES
- ✅ Automatyczne wykrywanie alternatywnych par tradingowych
- ⚠️ Pozostaje: rozbudowa tabel DB o SL/TP/leverage
