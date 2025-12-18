# 📊 ASE BOT - Kompleksowa Dokumentacja Systemu

## Spis treści
1. [Gdzie zapisywane są SL/TP](#1-gdzie-zapisywane-są-sltp)
2. [Jak działa śledzenie SL i TP](#2-jak-działa-śledzenie-sl-i-tp)
3. [Jak działa ustawianie dźwigni](#3-jak-działa-ustawianie-dźwigni)
4. [Jak działa ustawianie wielkości pozycji](#4-jak-działa-ustawianie-wielkości-pozycji)
5. [Jak działa ustawianie SL i TP](#5-jak-działa-ustawianie-sl-i-tp)
6. [Jak działa sprawdzanie dostępnej waluty](#6-jak-działa-sprawdzanie-dostępnej-waluty)
7. [Jak działa logika reewaluacji transakcji](#7-jak-działa-logika-reewaluacji-transakcji)
8. [Jak działa logika wchodzenia w transakcje](#8-jak-działa-logika-wchodzenia-w-transakcje)
9. [Gdzie bot zapisuje wykonane transakcje](#9-gdzie-bot-zapisuje-wykonane-transakcje)
10. [Wykryte luki](#10-wykryte-luki-i-problemy)

---

## 1. Gdzie zapisywane są SL/TP

### Lokalizacje przechowywania:

#### A. Baza danych Supabase (tabela `positions`)
```sql
-- Kolumny w tabeli positions:
stop_loss DECIMAL(20,8),
take_profit DECIMAL(20,8),
status VARCHAR, -- OPEN/CLOSED
```

**Plik:** `bot/db.py` - `DatabaseManager.save_position()`

#### B. W pamięci (Position Monitor)
```python
# bot/services/position_monitor.py
@dataclass
class MonitoredPosition:
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_enabled: bool = False
    dynamic_sl_enabled: bool = False
```

#### C. Ustawienia użytkownika (tabela `trading_settings`)
```sql
-- Domyślne wartości SL/TP użytkownika:
stop_loss_percentage DECIMAL(5,2), -- np. 5.0%
take_profit_percentage DECIMAL(5,2), -- np. 10.0%
```

### Flow zapisywania SL/TP:
```
1. Użytkownik → trading_settings (domyślne %)
2. Bot wchodzi w pozycję → positions (konkretne wartości ceny)
3. Position Monitor ładuje → pamięć (MonitoredPosition)
4. Aktualizacje trailing → positions (UPDATE stop_loss)
```

---

## 2. Jak działa śledzenie SL i TP

### Główny mechanizm: `PositionMonitorService`

**Plik:** `bot/services/position_monitor.py`

### Flow działania:
```
1. Bot uruchamia się → PositionMonitor.start()
2. Pętla co 5 sekund:
   a) Pobierz aktualne ceny z giełdy
   b) Dla każdej pozycji:
      - Sprawdź TIME EXIT (max 12h hold)
      - Sprawdź PARTIAL TP (3%, 5%, 7%)
      - Aktualizuj TRAILING STOP jeśli włączony
      - Sprawdź czy cena osiągnęła SL
      - Sprawdź czy cena osiągnęła TP
   c) Jeśli trigger → zamknij pozycję na giełdzie
   d) Zapisz trade do DB
```

### Kluczowe metody:
```python
# Główna pętla
async def _monitor_loop(self):
    while self.running:
        await self._check_all_positions()
        await asyncio.sleep(5)  # Co 5 sekund

# Sprawdzanie SL
if pos.side == 'long' and current_price <= pos.stop_loss:
    sl_triggered = True
elif pos.side == 'short' and current_price >= pos.stop_loss:
    sl_triggered = True

# Sprawdzanie TP
if pos.side == 'long' and current_price >= pos.take_profit:
    tp_triggered = True
```

### Trailing Stop Logic:
```python
# bot/services/position_monitor.py - _apply_trailing_stop()

# Dla LONG:
if profit_pct >= 1.0:  # Aktywacja po 1% zysku
    new_trailing_sl = highest_price - trailing_distance
    if new_trailing_sl > pos.stop_loss:  # Tylko podnosimy SL
        pos.stop_loss = new_trailing_sl
```

---

## 3. Jak działa ustawianie dźwigni

### Lokalizacja: `bot/exchange_adapters/ccxt_adapter.py`

### Flow:
```
1. Bot inicjalizuje adapter z margin=True
2. Przy składaniu zlecenia:
   - Kraken: automatycznie margin trading
   - Binance: wymaga set_leverage()
3. Domyślna dźwignia: 10x (z RiskManager)
```

### Kod:
```python
# ccxt_adapter.py
class CCXTAdapter:
    def __init__(self, ..., margin: bool = False):
        self.margin = margin
        if margin:
            market_type = 'margin'
        
    async def place_order(self, ...):
        if self.margin:
            params = {'type': 'margin'}
```

### ⚠️ LUKA: Brak automatycznego set_leverage() dla Binance
```python
# BRAKUJE:
async def set_leverage(self, symbol: str, leverage: int):
    await self.exchange.set_leverage(leverage, symbol)
```

---

## 4. Jak działa ustawianie wielkości pozycji

### Lokalizacja: `bot/services/risk_manager.py`

### Hierarchia obliczeń:
```
1. Kelly Criterion (jeśli > 5 trades historycznych)
2. ATR-based sizing (jeśli dostępne dane volatility)
3. Fixed percentage (fallback)
```

### Formula:
```python
# risk_manager.py - calculate_position_size()

# 1. Pobierz risk per trade (z ustawień użytkownika lub domyślne)
risk_per_trade = user_settings.risk_per_trade_percent / 100  # np. 0.02 dla 2%

# 2. Oblicz kwotę ryzyka
risk_amount = account_balance * risk_per_trade  # np. $1000 * 2% = $20

# 3. Oblicz wielkość pozycji
position_size = risk_amount / sl_distance  # np. $20 / $5 = 4 units

# 4. Zastosuj limity
position_size = min(position_size, max_position_size_usd / current_price)
```

### Ustawienia użytkownika (z `trading_settings`):
```python
class UserRiskSettings:
    risk_level: int = 3  # 1-5
    max_position_size: float = 1000.0
    
    @property
    def risk_per_trade_percent(self):
        risk_map = {1: 0.25, 2: 0.5, 3: 1.0, 4: 1.5, 5: 2.0}
        return risk_map[self.risk_level]
```

---

## 5. Jak działa ustawianie SL i TP

### Źródła wartości SL/TP:

#### A. Domyślne z ustawień użytkownika:
```python
# bot/services/risk_manager.py
def get_default_sl_tp(self, user_id: str) -> Tuple[float, float]:
    if user_id in self._user_settings:
        return (settings.stop_loss_percentage, settings.take_profit_percentage)
    return (5.0, 3.0)  # Domyślne: SL=5%, TP=3%
```

#### B. Dynamiczne (ATR-based):
```python
# risk_manager.py
atr = await self.calculate_atr(symbol)
sl_price = entry_price - (atr.atr * atr_multiplier_sl)  # np. entry - 2*ATR
tp_price = entry_price + (atr.atr * atr_multiplier_tp)  # np. entry + 3*ATR
```

#### C. Z sygnału AI:
```python
# auto_trader.py - analyze_market_with_ai()
signal = {
    'symbol': 'SOL/USDC',
    'action': 'BUY',
    'stop_loss': 124.507,   # Konkretna cena
    'take_profit': 140.234
}
```

#### D. Auto-set (jeśli brak):
```python
# position_monitor.py
if self.enable_auto_sl_tp and (stop_loss is None or take_profit is None):
    if side == 'long':
        stop_loss = entry_price * (1 - 5.0 / 100)   # -5%
        take_profit = entry_price * (1 + 7.0 / 100)  # +7%
```

---

## 6. Jak działa sprawdzanie dostępnej waluty

### Lokalizacja: `bot/auto_trader.py` - `manage_capital()`

### Flow:
```
1. Sprawdź USDT balance
   - Jeśli > $10 → używaj USDT
2. Sprawdź USDC balance
   - Jeśli > $10 → używaj USDC
3. Sprawdź FIAT (USD, EUR, PLN)
   - Jeśli > $10 → konwertuj na USDC
4. Fallback → USDT
```

### Kod:
```python
async def manage_capital(self) -> str:
    # Check USDT
    usdt_balance = await self.exchange.get_specific_balance("USDT")
    if usdt_balance > 10:
        return "USDT"

    # Check USDC
    usdc_balance = await self.exchange.get_specific_balance("USDC")
    if usdc_balance > 10:
        return "USDC"

    # Check FIAT and convert
    for currency in ["USD", "EUR", "GBP", "PLN"]:
        balance = all_balances.get(currency, 0)
        if balance > 10:
            await self.exchange.convert_currency(currency, "USDC", balance * 0.99)
            return "USDC"

    return "USDT"  # Fallback
```

### Dla Kraken:
```python
# ccxt_adapter.py
quote = 'USDC' if self.exchange.id == 'kraken' else 'USDT'
```

---

## 7. Jak działa logika reewaluacji transakcji

### A. Trailing Stop Reewaluacja
```
Co 5 sekund:
1. Pobierz aktualną cenę
2. Jeśli zysk >= 1%:
   - Oblicz nowy trailing SL
   - Jeśli nowy SL > stary SL → aktualizuj
3. Zapisz do DB (tabela position_reevaluations)
```

### B. Dynamic SL/TP Reewaluacja (co 60 sekund)
```python
# position_monitor.py - _apply_dynamic_sl_tp()
adjustment = await self.risk_manager.should_adjust_sl_tp(
    symbol=pos.symbol,
    current_price=current_price,
    current_sl=pos.stop_loss,
    current_tp=pos.take_profit
)
if adjustment.should_update:
    pos.stop_loss = adjustment.new_stop_loss
```

### C. Ghost Position Reconciliation (co 5 minut)
```python
# position_monitor.py - reconcile_ghost_positions()
# Porównuje pozycje w DB z pozycjami na giełdzie
# Zamyka "ghost" pozycje (w DB ale nie na giełdzie)
```

### Tabela reewaluacji:
```sql
CREATE TABLE position_reevaluations (
    position_id VARCHAR,
    reevaluation_type VARCHAR,  -- trailing_update, sl_triggered, tp_triggered
    old_sl DECIMAL,
    new_sl DECIMAL,
    old_tp DECIMAL,
    new_tp DECIMAL,
    current_price DECIMAL,
    profit_pct DECIMAL,
    reason TEXT,
    action_taken VARCHAR
);
```

---

## 8. Jak działa logika wchodzenia w transakcje

### Flow (trading_cycle):
```
1. PRE-TRADE CHECKS:
   ├── Daily Loss Tracker - czy nie przekroczono limitu?
   ├── Rate Limiter - ile trades dzisiaj?
   ├── Kill Switch - czy rynek nie jest ekstremalny?
   └── Market Sentiment - Fear & Greed Index

2. POBIERZ SYGNAŁY:
   ├── Z tabeli trading_signals (AI signals)
   └── Deduplikacja (preferuj najnowsze per symbol)

3. WALIDACJA SYGNAŁU:
   ├── Signal Validator - sprawdź konsensus
   ├── Confidence check (>= 70%)
   └── Portfolio correlation check

4. MARGIN CHECK:
   ├── get_margin_info() - ile wolnego marginu?
   ├── check_can_open_position() - czy stać na pozycję?
   └── Jeśli brak marginu → skip

5. POSITION SIZING:
   ├── Kelly Criterion
   ├── ATR-based sizing
   └── Max position limit

6. EXECUTE ORDER:
   └── place_order(symbol, side, quantity, sl, tp)

7. POST-TRADE:
   ├── Zapisz do DB (trades table)
   ├── Dodaj do Position Monitor
   └── Rate Limiter - record trade
```

### Kod entry point:
```python
# auto_trader.py - trading_cycle()
async def trading_cycle(self):
    # 1. Pre-checks
    if not self.daily_loss_tracker.can_open_new_trade(self.user_id):
        return  # Daily loss limit reached
    
    # 2. Get signals
    db_signals = self.get_signals_from_database(quote_currency)
    
    # 3. Validate
    validated = await self.analyze_market_with_ai(symbols, market_data, db_signals)
    
    # 4. Execute strategies
    for strategy in self.strategies:
        signals = strategy.analyze(market_data, positions)
        for signal in signals:
            if signal.confidence >= 0.7:
                await self.execute_signal(signal)
```

---

## 9. Gdzie bot zapisuje wykonane transakcje

### Tabela: `trades` (Supabase)

```sql
CREATE TABLE trades (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    exchange ENUM('kraken', 'binance'),
    symbol TEXT NOT NULL,
    trade_type ENUM('buy', 'sell'),
    amount NUMERIC,
    price NUMERIC,
    fee NUMERIC,
    status ENUM('pending', 'completed', 'failed'),
    source VARCHAR(50),  -- 'bot', 'manual', 'conversion'
    emotion TEXT,  -- Opis akcji: "🛑 Stop loss triggered"
    pnl NUMERIC,
    created_at TIMESTAMP
);
```

### Miejsca zapisu:

#### A. Przy otwarciu pozycji:
```python
# strategies.py - _save_trade_to_db()
db.save_trade(
    user_id=self.user_id,
    symbol=signal.symbol,
    trade_type="buy",
    price=price,
    amount=signal.quantity,
    source="bot"
)
```

#### B. Przy zamknięciu przez SL:
```python
# auto_trader.py - _on_sl_triggered()
db.save_trade(
    user_id=self.user_id,
    symbol=position.symbol,
    trade_type="sell",
    price=price,
    amount=position.quantity,
    source="bot",
    emotion="🛑 Stop loss triggered automatically"
)
```

#### C. Przy zamknięciu przez TP:
```python
# auto_trader.py - _on_tp_triggered()
db.save_trade(
    ...
    emotion="✅ Take profit triggered automatically"
)
```

#### D. Przy partial TP:
```python
# auto_trader.py - _on_partial_tp_triggered()
db.save_trade(
    ...
    emotion=f"🎯 Partial take profit level {level_index + 1}"
)
```

#### E. Przy time exit:
```python
# auto_trader.py - _on_time_exit_triggered()
db.save_trade(
    ...
    emotion=f"⏰ Time exit | P&L: {pnl_percent:+.2f}%"
)
```

---

## 10. Wykryte luki i problemy

### ✅ NAPRAWIONE (2025-12-13):

#### 1. **Duplikat ccxt_adapter.py - P0 Fix synchronized**
```
Lokalizacja: bot/http/ccxt_adapter.py
Problem: NIE MIAŁ P0 margin fix  
Status: ✅ NAPRAWIONE - dodano spot balance fallback
```

#### 2. **VaR Daily Check**
```
Lokalizacja: bot/services/risk_manager.py - calculate_var_daily()
Problem: Brak Value-at-Risk calculation
Status: ✅ NAPRAWIONE - dodano pełny VaR calculation z 95% confidence
Features:
  - Parametric VaR (z-score based)
  - 10% VaR threshold = halt trading
  - 5% VaR threshold = warning
```

#### 3. **Multi-Timeframe Confirmation**  
```
Lokalizacja: bot/services/risk_manager.py - check_multi_timeframe_confirmation()
Problem: Brak 4h/1d confirmation (false signals)
Status: ✅ NAPRAWIONE - dodano EMA cross check na 4h i 1d
Features:
  - EMA 9/21 trend detection
  - Majority confirmation required
  - Signal strength scoring
```

#### 4. **Session Filtering (Rollover Avoidance)**
```
Lokalizacja: bot/services/risk_manager.py - is_session_safe()
Problem: Trading podczas rollover/weekend
Status: ✅ NAPRAWIONE - dodano session safety check
Avoids:
  - Daily rollover (00:00 UTC ± 30 min)
  - Weekend gap (Friday 21:00 - Sunday 22:00 UTC)
```

#### 5. **Sharpe Live Calculation**
```
Lokalizacja: bot/services/risk_manager.py - calculate_sharpe_live()
Problem: Brak real-time Sharpe ratio
Status: ✅ NAPRAWIONE - dodano live Sharpe calculation
Features:
  - Annualized Sharpe
  - Quality scoring (excellent/good/acceptable/poor/negative)
  - can_scale flag dla position sizing
```

#### 6. **Correlation Matrix - Enhanced**
```
Lokalizacja: bot/core/correlation_manager.py
Problem: Niepełna macierz korelacji
Status: ✅ NAPRAWIONE - rozszerzona o XRP i więcej par
Added:
  - XRP correlations (8 pairs)
  - APT, SUI, STRK pairs
  - AI tokens (FET, AGIX, OCEAN, TAO)
  - Gaming tokens (AXS, SAND, MANA, GALA)
  - Total: ~90 correlation pairs
```

#### 7. **Pre-Trade Risk Check (Comprehensive)**
```
Lokalizacja: bot/auto_trader.py - signal filtering
Problem: Brak kompleksowego risk check przed trade
Status: ✅ NAPRAWIONE - dodano pre_trade_risk_check()
Checks:
  1. VaR limit check
  2. Multi-TF confirmation
  3. Session safety
  4. Sharpe quality
  5. Position size limits
  - Auto size adjustment based on risk factors
```

### 🔴 KRYTYCZNE (P0) - Pozostałe:

#### 8. **Brak automatycznego set_leverage() dla Binance**
```
Lokalizacja: ccxt_adapter.py
Problem: Dźwignia nie jest ustawiana przed otwarciem pozycji
Impact: Pozycje mogą być otwierane z domyślną dźwignią 1x
FIX: Dodać set_leverage() przed place_order()
```

### 🟠 WYSOKIE (P1) - Pozostałe:

#### 4. **Margin Check może zwracać $0.00 nawet gdy są środki**
```
Lokalizacja: ccxt_adapter.py - get_margin_info()
Problem: Dla Kraken zwraca free_margin=0 gdy nie ma otwartych pozycji
Impact: Bot nie może otwierać nowych pozycji
```

#### 5. **Brak synchronizacji SL/TP między giełdą a DB**
```
Problem: Giełda może mieć inne SL/TP niż DB (manual changes)
FIX: Dodać reconciliation przy starcie bota
```

#### 6. **Trading Settings nie ładują się dla wszystkich użytkowników**
```
Lokalizacja: auto_trader.py - _load_user_risk_settings()
Problem: Jeśli user nie ma wpisu w trading_settings, używa defaultów
```

### 🟡 ŚREDNIE (P2):

#### 7. **Rate Limiter reset przy restarcie bota**
```
Problem: Liczniki trade'ów są w pamięci, gubią się po restarcie
FIX: Zapisywać do Redis/DB
```

#### 8. **Partial TP nie zapisuje ilości pozostałej**
```
Problem: Po partial TP quantity w DB się nie aktualizuje
```

#### 9. **Time Exit nie sprawdza PnL przed zamknięciem**
```
Problem: Może zamknąć pozycję z dużą stratą bez ostrzeżenia
```

### 🟢 NISKIE (P3):

#### 10. **Brak alertów email o błędach krytycznych**
```
Problem: Alert service istnieje ale nie jest wszędzie używany
```

#### 11. **Trailing stop nie ma tiered levels zaimplementowanych**
```
Problem: Kod jest, ale nie jest aktywowany
```

---

## Podsumowanie architektury

```
┌─────────────────────────────────────────────────────────────┐
│                     AUTO_TRADER.PY                          │
│  (Główny koordynator - trading_cycle())                     │
└─────────────────────────────────┬───────────────────────────┘
                                  │
       ┌──────────────────────────┼──────────────────────────┐
       │                          │                          │
       ▼                          ▼                          ▼
┌──────────────┐        ┌─────────────────┐        ┌─────────────────┐
│  STRATEGIES  │        │ POSITION_MONITOR│        │  RISK_MANAGER   │
│  (Sygnały)   │        │  (SL/TP Watch)  │        │  (Sizing/SL/TP) │
└──────────────┘        └─────────────────┘        └─────────────────┘
       │                          │                          │
       │                          │                          │
       ▼                          ▼                          ▼
┌──────────────────────────────────────────────────────────────┐
│                     CCXT_ADAPTER.PY                          │
│  (Komunikacja z giełdą - Kraken/Binance)                     │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│                      SUPABASE (PostgreSQL)                   │
│  Tables: trades, positions, trading_settings, api_keys       │
└──────────────────────────────────────────────────────────────┘
```

---

*Dokument wygenerowany: 2025-12-13*
*Wersja bota: v3.0*
