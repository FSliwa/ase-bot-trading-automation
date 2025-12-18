# BOT CORE INFRASTRUCTURE v3.0 - Changelog

## Przegląd

Ten dokument opisuje wszystkie krytyczne poprawki wprowadzone do bota tradingowego w wersji 3.0.

## Nowe Moduły Core (`bot/core/`)

### 1. Symbol Normalizer (`symbol_normalizer.py`)
**Problem:** Różne formaty symboli w różnych komponentach (BTC, BTC/USDT, BTCUSDT)

**Rozwiązanie:**
- Ujednolicony format symboli w całym systemie
- Konwersja do formatu wewnętrznego: `BTC/USDT`
- Obsługa formatów specyficznych dla giełd (Kraken: XBT)

**Użycie:**
```python
from bot.core import SymbolNormalizer

normalizer = SymbolNormalizer()
symbol = normalizer.normalize("BTCUSDT")  # -> NormalizedSymbol
print(symbol.internal)  # "BTC/USDT"
print(symbol.base)      # "BTC"
```

---

### 2. Transaction Manager (`transaction_manager.py`)
**Problem:** Brak atomowych transakcji DB - zamówienie i pozycja zapisywane osobno

**Rozwiązanie:**
- Atomowe operacje DB z rollback przy błędach
- Wbudowana logika retry z exponential backoff
- Transakcyjne zapisywanie order + position

**Użycie:**
```python
from bot.core import TransactionManager

tm = TransactionManager(db_session)
async with tm.atomic_trade_execution(user_id, symbol) as ctx:
    order = await broker.place_order(...)
    ctx.record_order(order)
    ctx.record_position(position)
# Auto-commit lub rollback
```

---

### 3. Position Lock Manager (`position_lock.py`)
**Problem:** Race condition - bot i position monitor mogą zamknąć tę samą pozycję

**Rozwiązanie:**
- Mutex na poziomie symbolu
- Auto-expiring locks (zapobiega deadlocks)
- Śledzenie właściciela locka

**Użycie:**
```python
from bot.core import PositionLockManager

lock_mgr = PositionLockManager()
async with lock_mgr.acquire_lock("BTC/USDT", "trading_engine") as locked:
    if locked:
        await close_position(...)
```

---

### 4. Daily Loss Tracker (`daily_loss_tracker.py`)
**Problem:** `daily_loss_limit` ustawiony ale nigdy nie sprawdzany przed tradami

**Rozwiązanie:**
- Śledzenie dziennych strat per user
- Blokowanie nowych tradów po przekroczeniu limitu
- Pauza po serii strat (consecutive losses)

**Użycie:**
```python
from bot.core import DailyLossTracker

tracker = DailyLossTracker(max_daily_loss_pct=5.0)

if tracker.can_open_new_trade(user_id):
    # Execute trade
    tracker.record_trade(user_id, pnl=-50, is_win=False)
```

---

### 5. Correlation Manager (`correlation_manager.py`)
**Problem:** Sprawdzenie korelacji istnieje w risk_manager.py ale nie używane w strategies.py

**Rozwiązanie:**
- Limitowanie ekspozycji na skorelowane assety
- Tracking aktywnych pozycji i ich korelacji
- Blokowanie nowych pozycji gdy za dużo korelacji

**Użycie:**
```python
from bot.core import CorrelationManager

cm = CorrelationManager(max_correlation_exposure=0.5)
can_add, reason = cm.check_correlation_limit("ETH/USDT", "long", 1000)

if can_add:
    cm.add_position("ETH/USDT", "long", 1000)
```

---

### 6. Market Regime Sizer (`market_regime_sizer.py`)
**Problem:** Sentiment logowany ale nie wpływa na wielkość pozycji

**Rozwiązanie:**
- Dynamiczne dostosowanie wielkości pozycji
- Mnożniki bazowane na reżimie rynku
- Integracja z Fear & Greed Index

**Użycie:**
```python
from bot.core import MarketRegimeSizer, RegimeIndicators

sizer = MarketRegimeSizer()
indicators = RegimeIndicators(
    volatility_percentile=80,
    fear_greed_index=25,
    trend_direction=-1,
    trend_strength=70,
    ...
)

multiplier = sizer.get_size_multiplier(indicators=indicators, signal_direction="long")
adjusted_size = base_size * multiplier.final_multiplier
```

**Mnożniki reżimów:**
| Reżim | Mnożnik |
|-------|---------|
| CRISIS | 0.2 |
| CAPITULATION | 0.3 |
| EUPHORIA | 0.4 |
| HIGH_VOLATILITY | 0.5 |
| RECOVERY | 0.7 |
| TRENDING_BEARISH | 0.8 |
| RANGING | 1.0 |
| LOW_VOLATILITY | 1.1 |
| TRENDING_BULLISH | 1.2 |

---

### 7. Spread-Aware P&L Calculator (`spread_calculator.py`)
**Problem:** P&L kalkulowany bez uwzględnienia spreadu i opłat

**Rozwiązanie:**
- Kalkulacja efektywnej ceny entry/exit
- Uwzględnienie bid/ask spread
- Szacowanie slippage

**Użycie:**
```python
from bot.core import SpreadAwarePnL, SpreadData, FeeStructure

calc = SpreadAwarePnL(FeeStructure.binance_spot())
pnl = calc.calculate_pnl(
    side="long",
    quantity=0.1,
    entry_price=50000,
    current_price=51000,
    entry_spread=SpreadData(symbol="BTC/USDT", bid=49990, ask=50010),
    exit_spread=SpreadData(symbol="BTC/USDT", bid=50990, ask=51010)
)

print(f"Gross P&L: ${pnl.gross_pnl}")
print(f"Net P&L: ${pnl.net_pnl}")
print(f"Fee cost: ${pnl.fee_cost}")
```

---

### 8. Component Rate Limiter (`rate_limiter_v2.py`)
**Problem:** Globalny rate limiter, brak limitów per-component

**Rozwiązanie:**
- Osobne limity dla każdego komponentu
- trading_engine: 30 req/min
- position_monitor: 60 req/min
- market_data: 120 req/min

**Użycie:**
```python
from bot.core import ComponentRateLimiter

limiter = ComponentRateLimiter()
if await limiter.check("trading_engine"):
    # OK to proceed
    await place_order(...)
```

---

### 9. Retry Handler (`retry_handler.py`)
**Problem:** Brak retry logic dla krytycznych operacji (place_order, close_position)

**Rozwiązanie:**
- Exponential backoff z jitter
- Circuit breaker pattern
- Konfigurowalne polityki retry

**Użycie:**
```python
from bot.core import RetryHandler, with_retry, RetryPolicy

# Decorator
@with_retry(policy=RetryPolicy.CRITICAL, circuit_breaker="exchange_api")
async def place_order(...):
    ...

# Explicit handler
handler = RetryHandler()
result = await handler.execute_with_circuit_breaker(
    operation=api_call,
    circuit_name="api",
    args=(params,)
)
```

---

## Integracja z Istniejącym Kodem

### auto_trader.py
- Dodano import modułów core
- Inicjalizacja wszystkich managerów w `initialize()`
- Daily loss check przed każdym cyklem tradingowym
- Filtrowanie sygnałów przez correlation manager
- Regime-based position sizing
- Aktualizacja daily loss tracker przy SL/TP

### live_broker.py
- Position locking przy place_order
- Retry handler dla krytycznych operacji
- Symbol normalization

### position_monitor.py
- Position locking przy close_position
- Zapobieganie race conditions z trading engine

---

## Podsumowanie Poprawek

| # | Problem | Rozwiązanie | Moduł |
|---|---------|-------------|-------|
| 1 | Non-atomic DB operations | Transaction Manager | `transaction_manager.py` |
| 2 | Race conditions | Position Lock Manager | `position_lock.py` |
| 3 | Symbol inconsistency | Symbol Normalizer | `symbol_normalizer.py` |
| 4 | No spread in P&L | Spread Calculator | `spread_calculator.py` |
| 5 | Daily loss not enforced | Daily Loss Tracker | `daily_loss_tracker.py` |
| 6 | Correlation not used | Correlation Manager | `correlation_manager.py` |
| 7 | Sentiment not affecting size | Market Regime Sizer | `market_regime_sizer.py` |
| 8 | No retry logic | Retry Handler | `retry_handler.py` |
| 9 | Global rate limit only | Component Rate Limiter | `rate_limiter_v2.py` |

---

## Testowanie

Aby przetestować nowe moduły:

```bash
# Z katalogu projektu
cd /path/to/Algorytm\ Uczenia\ Kwantowego\ LLM

# Test imports
python -c "from bot.core import *; print('All core modules imported successfully')"

# Test specific module
python -c "
from bot.core import DailyLossTracker
tracker = DailyLossTracker(max_daily_loss_pct=5.0)
print(f'Can trade: {tracker.can_open_new_trade(\"test-user\")}')
"
```
