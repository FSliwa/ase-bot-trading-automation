# ASE BOT v2.0 - Kompletna Lista Funkcji

## Podsumowanie problemu SPOT Binance

### Problem zidentyfikowany:
Pozycje SPOT na Binance nie były automatycznie synchronizowane przy starcie bota, co powodowało:
1. Pozycje pokazywały się jako "unmonitored"
2. Bot liczył zbyt dużo pozycji (7/5 limit)
3. Pozycje nie miały SL/TP ustawionego

### Poprawki wprowadzone:

#### 1. `get_spot_balances()` w `ccxt_adapter.py`
```python
# PRZED: Zwracał wszystkie assety bez filtrowania dust
# PO: Filtruje dust pozycje (< $1 wartości) 
async def get_spot_balances(self, min_value_usd: float = 1.0) -> List[str]:
```

#### 2. `sync_from_exchange()` w `position_monitor.py`
```python
# PRZED: Nie retry, mylący log "No margin/futures positions"
# PO: 2 retry, lepszy log, działa dla SPOT/MARGIN/FUTURES
async def sync_from_exchange(self, db_manager=None, retry_count: int = 2) -> int:
```

### Wynik po poprawce:
```
📊 sync_from_exchange: Found 3 positions to sync
🛡️ AUTO-SET SL/TP for ZEC/USDT (1.0x leverage): SL=402.96 | TP=427.75
🔄 Synced exchange position: ZEC/USDT | SL=402.96 TP=427.75
🛡️ AUTO-SET SL/TP for GUN/USDT (1.0x leverage): SL=0.0246 | TP=0.0261
🔄 Synced exchange position: GUN/USDT | SL=0.0246 TP=0.0261
🛡️ AUTO-SET SL/TP for NXPC/USDT (1.0x leverage): SL=0.4049 | TP=0.4298
🔄 Synced exchange position: NXPC/USDT | SL=0.4049 TP=0.4298
✅ Synchronized 3 positions from exchange
```

---

# KOMPLETNA LISTA FUNKCJI ASE BOT

## 1. SYSTEM WIELOUŻYTKOWNIKOWY

### 1.1 Zarządzanie użytkownikami
- **Multi-tenant architecture** - każdy użytkownik ma własne:
  - Klucze API dla giełd (zaszyfrowane AES-256)
  - Ustawienia ryzyka i tradingu
  - Izolowane pozycje i monitoring

### 1.2 Obsługiwane giełdy
| Giełda | Tryby | Status |
|--------|-------|--------|
| **Kraken** | Spot, Futures | ✅ Produkcja |
| **Binance** | Spot, Margin | ✅ Produkcja |

### 1.3 Konfiguracja per user (`trading_settings`)
- `risk_level` - poziom ryzyka 1-5
- `risk_per_trade` - % kapitału na trade
- `max_position_size` - maksymalny rozmiar pozycji
- `stop_loss_percentage` - domyślny SL %
- `take_profit_percentage` - domyślny TP %
- `enable_margin_trading` - czy margin włączony
- `default_leverage` - domyślna dźwignia

---

## 2. POSITION MONITOR SERVICE

Plik: `bot/services/position_monitor.py` (3740 linii)

### 2.1 Konfiguracja bazowa
```python
PositionMonitorService(
    check_interval=5.0,        # Sprawdzanie co 5 sekund
    enable_trailing=True,      # Trailing Stop włączony
    enable_dynamic_sl=True,    # Dynamiczny SL włączony
    enable_partial_tp=True,    # Częściowe TP włączone
    enable_time_exit=True,     # Exit po czasie włączony
    enable_auto_sl_tp=True,    # Auto SL/TP dla nowych pozycji
)
```

### 2.2 STOP LOSS - Funkcje

#### 2.2.1 Podstawowy SL
- Zamknięcie całej pozycji gdy cena osiągnie poziom SL
- Linia: ~1600 `_handle_sl_trigger()`

#### 2.2.2 Trailing Stop Loss
- Automatyczne podnoszenie SL gdy cena rośnie
- `trailing_distance_percent` - domyślnie 2%
- Aktywacja po osiągnięciu minimalnego zysku
- Linia: ~1545 `_update_trailing_stop()`

```python
# Logika trailing:
if profit_pct >= min_profit_for_trailing:
    new_sl = current_price * (1 - trailing_distance/100)
    if new_sl > current_sl:
        update_sl(new_sl)
```

#### 2.2.3 Smart Break-Even
- Przesunięcie SL do entry price + buffer po osiągnięciu określonego zysku
- `break_even_trigger_pct` - 1.0% (domyślnie)
- `break_even_buffer_pct` - 0.1%
- Linia: ~2050 `_apply_break_even()`

#### 2.2.4 Dynamic SL/TP (ATR-based)
- SL/TP dostosowane do zmienności rynku
- Używa ATR (Average True Range)
- Risk:Reward ratio 1:1.5 minimum
- Linia: ~1815-1900

### 2.3 TAKE PROFIT - Funkcje

#### 2.3.1 Podstawowy TP
- Zamknięcie całej pozycji gdy cena osiągnie TP
- Linia: ~1680 `_handle_tp_trigger()`

#### 2.3.2 Partial Take Profit
- Zamknięcie części pozycji przy określonych poziomach zysku
- Domyślna konfiguracja:
```python
partial_tp_levels = [
    (30.0, 0.33),   # 30% zysku → zamknij 33%
    (50.0, 0.33),   # 50% zysku → zamknij 33%
    (70.0, 0.34),   # 70% zysku → zamknij 34%
]
```
- Linia: ~1740 `_check_partial_tp()`

#### 2.3.3 Momentum Scalper
- Exit przy 50% planowanego TP w ciągu 60 minut
- Tylko dla trybu scalping
- Konfiguracja:
```python
enable_momentum_scalp: bool = False
momentum_scalp_pct: float = 50.0     # % TP
momentum_scalp_minutes: int = 60     # Czas
```
- Linia: ~1900-1975 `_check_momentum_scalp_exit()`

### 2.4 CZAS - Exit po czasie

#### 2.4.1 Max Hold Time
- Automatyczne zamknięcie po X godzinach
- `max_hold_hours` - domyślnie 12h
- Linia: ~2100 `_check_time_based_exit()`

#### 2.4.2 Quick Exit (Scalping)
- Szybkie wyjście z zyskiem w krótkim czasie
```python
enable_quick_exit: bool = False
quick_exit_profit_pct: float = 0.5   # 0.5% zysku
quick_exit_time_minutes: float = 30  # W ciągu 30 min
```

### 2.5 LIQUIDATION MONITOR (v4.0)

- Monitorowanie ryzyka likwidacji dla pozycji z dźwignią
- `liquidation_warn_threshold` - 15% (ostrzeżenie)
- `auto_close_threshold` - 3.5% (auto-zamknięcie)
- Linia: ~3080-3180 `_check_liquidation_risk_all()`

```python
# Obliczenie ceny likwidacji
def calculate_liquidation_price(entry, leverage, side):
    if side == 'long':
        return entry * (1 - 1/leverage + maintenance_margin)
    else:  # short
        return entry * (1 + 1/leverage - maintenance_margin)
```

### 2.6 SYNCHRONIZACJA

#### 2.6.1 sync_from_database()
- Przywracanie pozycji z bazy danych po restarcie
- Linia: ~1050

#### 2.6.2 sync_from_exchange() [NAPRAWIONE]
- Synchronizacja pozycji z giełdy
- Działa dla SPOT, MARGIN i FUTURES
- Auto-ustawia SL/TP dla niechronionych pozycji
- Linia: ~1176

#### 2.6.3 reconcile_ghost_positions()
- Czyszczenie "duchów" - pozycji w DB które nie istnieją na giełdzie
- Linia: ~1315

#### 2.6.4 auto_sync_unmonitored()
- Automatyczne dodawanie niemonitorowanych pozycji
- Linia: ~3022

### 2.7 PRICE CACHE

- Cache cen dla szybkiego dostępu (5 sekund TTL)
- Linia: ~2260 `_update_price_cache()`

---

## 3. CCXT EXCHANGE ADAPTER

Plik: `bot/exchange_adapters/ccxt_adapter.py` (1361 linii)

### 3.1 Obsługiwane operacje
- `place_order()` - składanie zleceń
- `close_position()` - zamykanie pozycji
- `get_positions()` - pobieranie otwartych pozycji
- `get_balance()` - saldo konta
- `get_account_info()` - informacje o koncie
- `get_market_price()` - aktualna cena
- `get_ticker()` - pełne dane tickera
- `cancel_order()` - anulowanie zlecenia
- `set_leverage()` - ustawienie dźwigni

### 3.2 Tryby dla Binance
```python
# SPOT mode
if exchange.id == 'binance' and not futures:
    return _get_spot_positions_with_entry_price()

# MARGIN mode  
if margin:
    return _get_margin_positions()

# FUTURES mode
positions = await exchange.fetch_positions()
```

### 3.3 Obsługa reduce_only
```python
# SPOT nie wspiera reduce_only
if reduce_only:
    if self.futures or self.margin:
        params['reduceOnly'] = True
    else:
        # SPOT - ignoruj
        logger.debug("Ignoring reduce_only for SPOT mode")
```

### 3.4 Dust Position Filtering [NAPRAWIONE]
```python
# Filtrowanie pozycji o niskiej wartości (< $1)
MIN_VALUE_USD = 1.0
DUST_THRESHOLD = 0.0001

if position_value < MIN_VALUE_USD:
    logger.info(f"🧹 Skipping low-value position: {symbol}")
    continue
```

---

## 4. RISK MANAGER

Plik: `bot/services/risk_manager.py`

### 4.1 Position Sizing
- **Kelly Criterion** - optymalne wielkości pozycji
- **Volatility-adjusted** - dostosowane do zmienności
- **Max position limit** - limit wielkości pozycji

### 4.2 Circuit Breakers
- Automatyczne zatrzymanie tradingu przy:
  - Max daily loss
  - Max drawdown
  - Zbyt wiele stratnych trade'ów z rzędu

### 4.3 Dynamic SL/TP
- Bazowane na ATR (Average True Range)
- Minimum Risk:Reward 1:1.5
- Dostosowane do reżimu rynkowego (bear/bull/sideways)

### 4.4 Leverage-Aware SL/TP
```python
# SL/TP jako % kapitału, nie ceny
# 5% SL z 10x leverage = 0.5% ruchu ceny
effective_sl_pct = sl_pct / leverage
```

---

## 5. PORTFOLIO MANAGER

Plik: `bot/services/portfolio_manager.py`

### 5.1 Limity ekspozycji
```python
max_single_position_pct = 25.0      # Max 25% w jednej pozycji
max_category_exposure_pct = 40.0    # Max 40% w jednej kategorii
max_l1_exposure_pct = 400.0         # Max 400% L1 tokens
max_meme_exposure_pct = 10.0        # Max 10% meme coiny
max_defi_exposure_pct = 50.0        # Max 50% DeFi
min_stable_reserve_pct = 10.0       # Min 10% stable reserve
```

### 5.2 Korelacja
- Analiza korelacji między pozycjami
- Ostrzeżenie przy wysokiej koncentracji

### 5.3 Decyzje tradingowe
- Blokowanie trade'ów przy przekroczeniu limitów
- Size multiplier dla ostrożności

---

## 6. AI SIGNAL PROCESSING

### 6.1 Źródła sygnałów
- **COUNCIL_V2.0_FALLBACK** - główny system AI
- **titan_v3** - alternatywny system
- Zaufane źródła z tabeli `trading_signals`

### 6.2 Signal Validator
```python
SignalValidator(
    min_confidence=0.6,
    require_confluence=True,
    max_age_hours=6,
)
```

### 6.3 Signal Deduplicator
- Okno 6 godzin
- Preferowanie nowszych sygnałów
- Unikanie duplikatów

---

## 7. DCA MANAGER

Plik: `bot/services/dca_manager.py`

### 7.1 Konfiguracja
```python
base_order_pct = 40.0       # 40% kapitału w first order
safety_order_count = 3       # 3 safety orders
price_deviation_pct = 3.0    # 3% między orderami
safety_order_volume_scale = 1.5
safety_order_step_scale = 1.2
```

### 7.2 Logika
- Automatyczne uśrednianie ceny przy spadkach
- Obliczanie breakeven po DCA orders

---

## 8. MARKET INTELLIGENCE

Plik: `bot/services/market_intelligence.py`

### 8.1 Liquidity Check
- Spread analysis
- Slippage estimation
- Max safe trade size

### 8.2 Sentiment Analysis
- Fear & Greed Index
- Market regime detection (bull/bear/sideways)

### 8.3 Dynamic Parameters
- SL/TP adjustment based on volatility
- Position sizing based on conditions

---

## 9. RATE LIMITER

Plik: `bot/services/rate_limiter.py`

### 9.1 Limity
```python
max_trades_per_cycle = 3
max_trades_per_hour = 5
max_trades_per_day = 15
```

### 9.2 Logika
- Blokowanie nadmiernego tradingu
- Cooldown po serii trade'ów

---

## 10. WEBSOCKET MANAGER

Plik: `bot/realtime/websocket_manager.py`

### 10.1 Funkcje
- Real-time price updates
- Ticker streaming dla BTC/USDT, ETH/USDT
- Obsługa reconnect

---

## 11. TRADING MODES

Plik: `bot/trading_config/trading_modes.py`

### 11.1 Dostępne tryby

#### SCALPING
```python
scalping_config = TradingModeConfig(
    min_rr_ratio=1.2,
    max_hold_hours=4.0,
    stop_loss_atr_multiplier=1.0,
    take_profit_atr_multiplier=1.5,
    enable_trailing=True,
    trailing_trigger_pct=0.5,
    enable_break_even=True,
    break_even_trigger_pct=0.5,
    enable_momentum_scalp=True,     # ← Momentum Scalper
    momentum_scalp_pct=50.0,
    momentum_scalp_minutes=60,
)
```

#### SWING
```python
swing_config = TradingModeConfig(
    min_rr_ratio=2.0,
    max_hold_hours=168.0,  # 7 dni
    stop_loss_atr_multiplier=2.0,
    take_profit_atr_multiplier=4.0,
    enable_trailing=True,
    trailing_trigger_pct=3.0,
)
```

#### POSITION
```python
position_config = TradingModeConfig(
    min_rr_ratio=3.0,
    max_hold_hours=720.0,  # 30 dni
    stop_loss_atr_multiplier=3.0,
    take_profit_atr_multiplier=6.0,
)
```

---

## 12. DATABASE STRUCTURE

### 12.1 Główne tabele
- `users` - użytkownicy
- `api_keys` - klucze API (zaszyfrowane)
- `trading_settings` - ustawienia tradingu per user
- `risk_management_settings` - ustawienia ryzyka
- `positions` - pozycje (otwarte i zamknięte)
- `trades` - wykonane trade'y
- `trading_signals` - sygnały AI
- `reevaluation_history` - historia reewaluacji
- `user_notifications` - powiadomienia

### 12.2 Position Status
- `OPEN` - otwarta
- `CLOSED` - zamknięta
- `PENDING` - oczekująca

---

## 13. STRATEGIE TRADINGOWE

Plik: `bot/strategies.py`

### 13.1 TradingStrategies
- Momentum Strategy
- Mean Reversion Strategy
- Breakout Strategy

### 13.2 Signal Processing
- Analiza sygnałów z AI
- Walidacja z konfluencją
- Portfolio-aware decisions

---

## 14. BROKER (LiveBroker)

Plik: `bot/broker/live_broker.py`

### 14.1 Funkcje
- Order execution
- Position management
- Error handling
- Retry logic

---

## 15. LOGOWANIE I MONITORING

### 15.1 Logi
- `bots_live.log` - główny log
- `monitor_group.log` - log monitoringu

### 15.2 Poziomy logów
- INFO - normalne operacje
- WARNING - ostrzeżenia (SL triggers, etc.)
- ERROR - błędy

### 15.3 Emoji w logach
- 🚀 Start
- ✅ Sukces
- ⚠️ Ostrzeżenie
- 🛑 Stop Loss
- 🎯 Take Profit
- 📊 Dane
- 🧹 Dust cleanup
- 🔄 Sync
- 💾 Persistence
- 🚨 Liquidation

---

## Podsumowanie

ASE BOT v2.0 to zaawansowany system tradingowy z:

1. **27+ głównych funkcji** zarządzania pozycjami
2. **Multi-user architecture** z izolacją
3. **Real-time monitoring** co 5 sekund
4. **AI-driven signals** z walidacją
5. **Risk management** z circuit breakers
6. **Portfolio awareness** z limitami ekspozycji
7. **Flexible exit strategies** (SL/TP/trailing/partial/time)

Data dokumentacji: 2025-12-15
Autor: ASE BOT System
