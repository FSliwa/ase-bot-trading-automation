# Exchange and SPOT Trading Constraints - Implementation

## Data: 21 października 2025

## Zmiany wprowadzone

### 1. Aktualizacja promptu analizy Claude (bot/ai_analysis.py)

Dodano dynamiczne ograniczenia handlowe w `analyze_market()`:

```python
# Dodanie informacji o giełdzie i ograniczeniach SPOT
exchange = parameters.get("exchange", "unknown").lower()
trading_constraints = ""
if exchange == "binance":
    trading_constraints = (
        "\n[CRITICAL TRADING CONSTRAINTS]\n"
        "• Exchange: Binance\n"
        "• Trading Type: SPOT ONLY (no futures, no margin, no leverage)\n"
        "• All recommendations MUST be for SPOT market pairs only\n"
        "• User can ONLY trade spot assets (buy/sell without leverage)\n"
    )
elif exchange != "unknown":
    trading_constraints = f"\n[Trading Context]\n• Exchange: {exchange}\n"
```

**Efekt**: Claude Opus otrzymuje wyraźną informację o:
- Z jakiej giełdy korzysta użytkownik
- Że dla Binance dozwolony jest TYLKO SPOT trading (bez dźwigni, margin, futures)
- Wszystkie rekomendacje muszą być dla par SPOT

### 2. Aktualizacja walidacji Gemini (bot/ai_analysis.py)

Dodano analogiczne ograniczenia do `_validate_with_gemini()`:

```python
exchange = (analysis.get("context_sources", {}).get("exchange", "unknown")).lower()
trading_constraints = ""
if exchange == "binance":
    trading_constraints = (
        "\n[CRITICAL VALIDATION REQUIREMENT]\n"
        "• User Exchange: Binance\n"
        "• Trading Type: SPOT ONLY (no futures, no margin, no leverage)\n"
        "• Verify ALL recommendations are for SPOT market pairs only\n"
        "• Flag any suggestions involving leverage, margin, or futures as REJECT\n"
    )
```

**Efekt**: Gemini podczas walidacji:
- Sprawdza zgodność rekomendacji z ograniczeniem SPOT
- Odrzuca (REJECT) wszelkie sugestie z dźwignią/margin/futures
- Weryfikuje, czy wszystkie rekomendacje są dla rynku SPOT

### 3. Przechowywanie exchange w context_sources

Dodano zapis informacji o giełdzie w odpowiedzi AI:

```python
json_response["context_sources"]["exchange"] = parameters.get("exchange", "unknown")
```

**Efekt**: Informacja o giełdze jest:
- Przechowywana w odpowiedzi JSON
- Dostępna dla walidacji Gemini
- Zapisywana w bazie danych (w payload analiz)

## Jak to działa

### Przepływ danych:

1. **auto_trader.py** wywołuje `analyze_market()` z parametrem:
   ```python
   analysis = await self.market_analyzer.analyze_market({
       "notional": "10000",
       "max_leverage": str(self.config.max_leverage),
       "exchange": self.exchange_name  # ← przekazywane z ENV
   })
   ```

2. **bot/ai_analysis.py** odbiera exchange i:
   - Dodaje sekcję `[CRITICAL TRADING CONSTRAINTS]` do promptu Claude
   - Zapisuje exchange w `context_sources`
   - Przekazuje do walidacji Gemini

3. **Claude Opus** otrzymuje prompt z wyraźnymi ograniczeniami:
   ```
   [CRITICAL TRADING CONSTRAINTS]
   • Exchange: Binance
   • Trading Type: SPOT ONLY (no futures, no margin, no leverage)
   • All recommendations MUST be for SPOT market pairs only
   • User can ONLY trade spot assets (buy/sell without leverage)
   
   [Market Parameters]
   {
     "notional": "10000",
     "max_leverage": "1",
     "exchange": "binance"
   }
   ```

4. **Gemini walidacja** sprawdza:
   - Czy rekomendacje nie zawierają dźwigni
   - Czy wszystkie pary to SPOT
   - Czy nie ma sugestii margin/futures

## Źródło danych exchange

### Obecnie (auto_trader.py):
```python
self.exchange_name = os.getenv("EXCHANGE_NAME", "binance")
```

### W przyszłości (dla wielu użytkowników):
Można rozszerzyć o pobieranie z `TradingSettings`:

```python
with DatabaseManager() as db:
    settings = db.session.query(TradingSettings)\
        .filter(TradingSettings.user_id == user_id)\
        .filter(TradingSettings.is_trading_enabled == True)\
        .first()
    
    if settings:
        exchange = settings.exchange  # 'binance', 'coinbase', etc.
```

## Testowanie

### Przykładowe wywołanie:
```python
analyzer = MarketAnalyzer()
result = await analyzer.analyze_market({
    "symbol": "BTC/USDT",
    "notional": "10000",
    "exchange": "binance"
})

# Result będzie zawierać:
# - recommendations dla SPOT only
# - context_sources.exchange = "binance"
# - validation z flagami jeśli wykryto naruszenia
```

### Weryfikacja w logach:
```python
logger.info(f"Analysis for {exchange} with SPOT constraints")
logger.info(f"Validation status: {result['validation']['status']}")
logger.info(f"Risk flags: {result['validation']['risk_flags']}")
```

## Zgodność z innymi giełdami

Kod obsługuje również inne giełdy:
- Dla Binance: **SPOT ONLY** (ścisłe ograniczenie)
- Dla innych giełd: informacja o exchange bez ograniczeń SPOT (można rozszerzyć)

```python
elif exchange != "unknown":
    trading_constraints = f"\n[Trading Context]\n• Exchange: {exchange}\n"
```

## Integracja z bazą danych (Supabase)

Tabela `trading_settings` zawiera:
- `exchange` (TEXT) - nazwa giełdy użytkownika
- `user_id` (UUID) - identyfikator użytkownika
- `risk_level` (INTEGER) - poziom ryzyka (1-5)

Można rozszerzyć o:
- `trading_type` (TEXT) - 'spot', 'margin', 'futures' (enum)
- `max_leverage` (NUMERIC) - maksymalna dźwignia (1 dla SPOT)

## Zalecenia

### 1. Dodaj kolumnę trading_type do trading_settings:
```sql
ALTER TABLE public.trading_settings 
ADD COLUMN trading_type TEXT DEFAULT 'spot' CHECK (trading_type IN ('spot', 'margin', 'futures'));
```

### 2. Dla Binance SPOT wymuszaj trading_type = 'spot':
```python
if exchange == 'binance' and settings.trading_type != 'spot':
    raise ValueError("Binance users can only use SPOT trading")
```

### 3. Rozszerz walidację o trading_type:
```python
if exchange == 'binance' and analysis.get('leverage', 1) > 1:
    validation['status'] = 'reject'
    validation['risk_flags'].append('leverage_not_allowed_for_binance_spot')
```

## Status implementacji

✅ **Zrobione**:
- Dodano ograniczenia SPOT do promptu Claude
- Dodano walidację SPOT w Gemini
- Zapisywanie exchange w context_sources
- Przekazywanie exchange z auto_trader

⏳ **Do zrobienia** (opcjonalnie):
- Dodanie kolumny trading_type do trading_settings
- Pobranie exchange z bazy dla wielu użytkowników (obecnie z ENV)
- Frontend: wyświetlanie ograniczeń SPOT dla użytkowników Binance
- Testy jednostkowe dla różnych exchange i trading_type

## Pliki zmodyfikowane

1. `/bot/ai_analysis.py`:
   - Metoda `analyze_market()` - dodano trading_constraints
   - Metoda `_validate_with_gemini()` - dodano walidację SPOT
   - Zapisywanie exchange w context_sources

## Przykładowa odpowiedź AI (z ograniczeniami SPOT):

```json
{
  "model_used": "claude-3-opus-latest",
  "context_sources": {
    "tavily_search": "...",
    "exchange": "binance"
  },
  "market_regime": {
    "trend": "bullish",
    "volatility_state": "normal"
  },
  "top_pick": {
    "symbol": "BTC/USDT",
    "action": "buy",
    "why": "Strong SPOT momentum without leverage",
    "conditions": "SPOT trading only, no margin"
  },
  "validation": {
    "status": "approve",
    "reasoning": "All recommendations are SPOT-only, no leverage detected",
    "risk_flags": [],
    "model": "gemini-2.0-pro-latest"
  }
}
```
