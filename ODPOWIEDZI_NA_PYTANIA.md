# 📋 ODPOWIEDZI NA PYTANIA - ASE BOT v3.0

> **Data:** 14 grudnia 2025

---

## 1. GDZIE JEST ZAPISYWANE SL TP?

### ✅ Odpowiedź:

| Lokalizacja | Typ | Tabela/Struktura | Pola |
|-------------|-----|------------------|------|
| **Supabase PostgreSQL** | Permanentna | `trades` | `stop_loss`, `take_profit` |
| **Supabase PostgreSQL** | Permanentna | `positions` | `stop_loss`, `take_profit` |
| **Supabase PostgreSQL** | Permanentna | `trading_signals` | `stop_loss`, `take_profit`, `entry_price` |
| **In-Memory** | Runtime | `MonitoredPosition` dataclass | `stop_loss`, `take_profit`, `original_stop_loss` |

### 📁 Pliki:

- `bot/db.py` - Modele SQLAlchemy (Trade, Position, TradingSignal)
- `bot/services/position_monitor.py` - `MonitoredPosition` dataclass

### ⚠️ UWAGA:

Trailing stop updates są TYLKO in-memory - nie są zapisywane do DB. Po restarcie bota - utrata zaktualizowanych SL.

---

## 2. JAK DZIAŁA ŚLEDZENIE SL I TP?

### ✅ Odpowiedź:

**PositionMonitorService** sprawdza co **5 sekund**:

```
┌─────────────────────────────────────────┐
│  _monitor_loop() - każde 5 sekund       │
├─────────────────────────────────────────┤
│ 1. Pobierz aktualną cenę (REST API)     │
│ 2. Dla każdej pozycji sprawdź:          │
│    • LONG SL: price <= stop_loss        │
│    • LONG TP: price >= take_profit      │
│    • SHORT SL: price >= stop_loss       │
│    • SHORT TP: price <= take_profit     │
│ 3. Jeśli triggered → callback           │
│ 4. Update trailing stop jeśli enabled   │
└─────────────────────────────────────────┘
```

### 📁 Plik: `bot/services/position_monitor.py`

### ⚠️ LUKA:

To są "software stops" - monitorowane przez bota, NIE przez giełdę. Gdy bot offline = BRAK ochrony!

---

## 3. JAK DZIAŁA USTAWIANIE DŹWIGNI?

### ✅ Odpowiedź:

```
┌─────────────────────────────────────────┐
│         LEVERAGE DECISION TREE          │
├─────────────────────────────────────────┤
│ 1. SPOT MODE? → leverage = 1 (FORCED)   │
│                                         │
│ 2. MARGIN/FUTURES MODE:                 │
│    • Kraken: params['leverage']         │
│    • Binance: set_leverage_safe() API   │
│                                         │
│ 3. Cap at exchange maximum              │
└─────────────────────────────────────────┘
```

### 📁 Plik: `bot/http/ccxt_adapter.py` (linie 752-790)

### Kod:
```python
is_spot_mode = not self.futures and not self.margin

if is_spot_mode:
    actual_leverage = 1  # SPOT NEVER has leverage (L3 FIX)
elif leverage:
    if self.exchange.id == 'kraken':
        actual_leverage = await self.get_best_leverage(symbol, leverage)
        params['leverage'] = actual_leverage
    elif self.exchange.id == 'binance':
        actual_leverage = await self.set_leverage_safe(symbol, leverage)
```

---

## 4. JAK DZIAŁA USTAWIANIE WIELKOŚCI POZYCJI?

### ✅ Odpowiedź:

**Pipeline:**
```
1. Kelly Criterion (jeśli 20+ trades)
   └── f* = (bp - q) / b
   └── Progressive: 10% → 25% Kelly
   
2. Volatility-Adjusted Size
   └── Size = (Capital × Risk%) / (Price × SL Distance)
   └── ATR multiplier
   
3. Take MINIMUM(Kelly, Volatility)

4. Apply confidence multiplier (50%-100%)

5. Cap at user's max_position_size

6. Validate vs exchange minimum
   └── If below: INCREASE to min OR REJECT
```

### 📁 Plik: `bot/services/risk_manager.py` (linie 1050-1150)

---

## 5. JAK DZIAŁA USTAWIANIE SL I TP?

### ✅ Odpowiedź:

**Źródła SL/TP (priorytet):**

1. **Signal-Provided** - z `trading_signals` table (AI)
2. **Dynamic ATR-Based** - `SL = entry - (ATR × 2.0)`, `TP = entry + (ATR × 3.0)`
3. **User Default %** - z ustawień użytkownika (K1 FIX: leverage-aware!)
4. **System Default** - 5% SL, 7% TP

### K1 FIX - Leverage-Aware:
```python
if leverage_aware and leverage > 1.0:
    effective_sl_pct = sl_pct / leverage  # 5% / 10x = 0.5%
    effective_tp_pct = tp_pct / leverage
```

### 📁 Plik: `bot/services/position_monitor.py` (linie 320-370)

---

## 6. SPRAWDZANIE DOSTĘPNEJ WALUTY

### ✅ Odpowiedź:

**`manage_capital()` cascade:**

```
1. Check USDT balance → if > $10 → USE USDT
2. Check USDC balance → if > $10 → USE USDC
3. Check FIAT (USD, EUR, GBP, PLN) → AUTO-CONVERT to USDC
4. Fallback → USDT
```

### 📁 Plik: `bot/auto_trader.py` (linie 1380-1420)

### ⚠️ LUKA K6:

Isolated margin balance NIE jest wykrywany! User e4f7f9e4 ma 79 USDC na isolated margin ale bot widzi 0.

---

## 7. LOGIKA REEWALUACJI

### ✅ Odpowiedź:

**Pre-Trade Checks:**
- ✅ Daily Loss Tracker (max 5% daily loss)
- ✅ Rate Limiter (max trades/hour, trades/day)
- ✅ Kill Switch (extreme market conditions)
- ✅ Correlation Manager (max exposure per correlated group)
- ✅ VaR Check

**Signal Validation:**
- ✅ Signal Age Check (max 5 min)
- ✅ Duplicate Detection
- ✅ Confidence Threshold (min 10%)

**Position Monitoring (każde 5s):**
- ✅ Dynamic SL/TP adjustment
- ✅ Trailing Stop updates
- ✅ Time-based exit (12h default)

### ⚠️ LUKA W3:

Brak periodic signal reassessment - sygnał wykonany = brak dalszej oceny czy warunki rynkowe nadal wspierają pozycję.

---

## 8. LOGIKA WCHODZENIA W TRANSAKCJE

### ✅ Odpowiedź:

**Full Pipeline:**

```
KROK 1: SIGNAL ACQUISITION
├── PRIMARY: trading_signals table (titan_v3)
└── FALLBACK: Edge Function AI (COUNCIL V2.0)

KROK 2: SIGNAL FILTERING
├── Age filter (< 5 min)
├── Confidence filter (> 10%)
├── Exchange compatibility
└── Deduplication

KROK 3: RISK CHECKS
├── Daily loss limit
├── Rate limiter
├── Kill switch
├── Correlation limit
└── Pre-trade VaR

KROK 4: POSITION SIZING
├── Kelly Criterion
├── Volatility adjustment
├── Confidence multiplier
├── User max cap
└── Exchange minimum validation

KROK 5: ORDER EXECUTION
├── Quantity adjustment
├── Leverage setting
├── SL/TP params
└── Order placement

KROK 6: POST-TRADE
├── Save to trades table
├── Add to Position Monitor
├── Update correlation manager
└── Log to trading_signals
```

### 📁 Plik: `bot/auto_trader.py` (linie 1000-1700)

---

## 9. ZAPISYWANIE TRANSAKCJI W SUPABASE

### ✅ Odpowiedź:

**Events zapisywane do `trades` table:**

| Event | Metoda | Dane |
|-------|--------|------|
| Order executed | `db.save_trade()` | symbol, price, amount, SL, TP, leverage |
| SL triggered | `_on_sl_triggered()` | pnl, exit_price, emotion |
| TP triggered | `_on_tp_triggered()` | pnl, exit_price, emotion |
| Partial TP | `_on_partial_tp_triggered()` | partial amount, level |
| Time exit | `_on_time_exit_triggered()` | exit_price, pnl |

### 📁 Plik: `bot/db.py` (linie 1040-1090)

### Kod save_trade():
```python
def save_trade(self, *, user_id, symbol, trade_type, price, amount,
               pnl=None, source="bot", emotion=None, exchange="kraken",
               stop_loss=None, take_profit=None, leverage=None,
               entry_price=None, exit_price=None):
```

---

## 10. ZIDENTYFIKOWANE LUKI

### 🔴 KRYTYCZNE (DO NATYCHMIASTOWEJ NAPRAWY):

| # | Luka | Status |
|---|------|--------|
| K1 | SL/TP nie uwzględnia leverage | ✅ NAPRAWIONE |
| K3 | Edge Function empty response | ✅ NAPRAWIONE |
| K5 | Software stops only (no exchange SL/TP) | ❌ DO NAPRAWY |
| K6 | Isolated margin balance not detected | ❌ DO NAPRAWY |
| K7 | No transaction atomicity | ❌ DO NAPRAWY |
| K8 | No order fill verification | ❌ DO NAPRAWY |
| K9 | No WebSocket real-time price feeds | ❌ DO NAPRAWY |

### 🟠 WYSOKIE:

| # | Luka |
|---|------|
| W1 | Trailing stop not persisted to DB |
| W2 | No order fill verification |
| W3 | No periodic signal reassessment |
| W4 | Kelly cold start problem |
| W5 | Async callback może być fire-and-forget |
| W6 | User settings cache not invalidated |
| W7 | No order book depth check |

---

## PODSUMOWANIE

**Stan systemu po K1/K3 FIX:** 7/10

**Mocne strony:**
- ✅ Kompleksowy position sizing (Kelly + Volatility)
- ✅ Leverage-aware SL/TP (K1 FIX)
- ✅ Multi-layer risk checks
- ✅ AI signals (COUNCIL V2.0)

**Krytyczne do naprawy:**
- ❌ Exchange-native SL/TP orders
- ❌ Isolated margin detection
- ❌ Transaction atomicity
- ❌ Order fill verification

**Po naprawie K5-K9:** 8.5/10

---

*Pełna analiza: `DEEP_SYSTEM_ANALYSIS_v2.md`*
