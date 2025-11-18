## PrimeXBT Trading Bot (MVP)

Bezpieczne, minimalne MVP bota do składania zleceń tradingowych zgodnie z założeniami: domyślnie paper trading, bez sekretów w repo, bramka bezpieczeństwa dla trybu live, parser poleceń oparty na regułach, warstwa HTTP z metodami NotImplementedError do późniejszego uzupełnienia.

### Najważniejsze cechy
- Paper trading z wbudowanym symulatorem (`PaperBroker`) – stan tylko w pamięci procesu.
- Tryb live wymaga jawnego włączenia (`--live`) oraz potwierdzenia (`--confirm-yes` lub `CONFIRM=YES`).
- Brak sekretów w repo – używaj zmiennych środowiskowych lub pliku `.env` (zob. `.env.example`).
- Logi sanityzowane – klucze i sekrety nie są logowane wprost.
- Parser komend (PL/EN) przez proste reguły/regexy.
- Warstwa HTTP `PrimeXbtHttpClient` – metody rzucają `NotImplementedError` do uzupełnienia zgodnie z oficjalną dokumentacją PrimeXBT.

### Szybki start
1) Utwórz i aktywuj środowisko:
```
python3 -m venv .venv
source .venv/bin/activate
```

2) Zainstaluj zależności:
```
pip install -r requirements.txt
```

3) Skonfiguruj `.env` na bazie `.env.example` (opcjonalne dla paper trading):
```
cp .env.example .env
```

4) Uruchom pomoc CLI:
```
python -m bot.cli --help
```

### Użycie (paper trading – domyślnie)
Przykładowe polecenie (PL):
```
python -m bot.cli trade "kup 0.01 BTCUSDT limit 60000 SL 58500 TP 61500 lev 3x"
```

Przykładowe polecenie (EN):
```
python -m bot.cli trade "buy 0.01 BTCUSDT market SL 58500 TP 61500 lev 3x"
```

Status pozycji (paper):
```
python -m bot.cli status
```

Zamknięcie pozycji:
```
python -m bot.cli close-position BTCUSDT
```

Symulacyjna cena (opcjonalnie) – gdy chcesz jawnie wskazać cenę w paper trading:
```
python -m bot.cli trade "buy 0.01 BTCUSDT market SL 58500" --price 60250
```

### Tryb live (nieaktywne domyślnie)
Włączenie live wymaga jednocześnie flagi `--live` i potwierdzenia:
```
export CONFIRM=YES
python -m bot.cli trade "buy 0.01 BTCUSDT market SL 58500" --live
# lub
python -m bot.cli trade "buy 0.01 BTCUSDT market SL 58500" --live --confirm-yes
```

UWAGA: w trybie live metody `PrimeXbtHttpClient` wymagają uzupełnienia zgodnie z oficjalną dokumentacją PrimeXBT i obecnie rzucają `NotImplementedError`.

## Backend API i usługi towarzyszące

Repozytorium zostało oczyszczone z wszelkich zasobów frontendowych. Dostęp do danych oraz funkcji bota odbywa się wyłącznie przez API oraz narzędzia konsolowe.

### Uruchamianie FastAPI

- szybki start: `uvicorn app:app --host 0.0.0.0 --port 8008`
- z automatycznym zarządzaniem procesami: `python backend_system_startup.py`

Skrypt `backend_system_startup.py` uruchamia jedynie usługi backendowe (API oraz opcjonalny silnik analityczny), zapewnia logowanie i bezpieczne zamykanie procesów. Nie ma już zależności od serwerów HTML ani pakietów Node.js.

### Integracja z innymi klientami

- wszystkie trasy HTTP znajdziesz w katalogu `api/`
- wywołania programistyczne można wykonywać z dowolnego klienta HTTP/Auth
- nagłówki CORS dopuszczają tylko lokalne adresy (`localhost`, `127.0.0.1`). W przypadku wdrożeń zewnętrznych dostosuj konfigurację CORS w pliku `app.py`

### Konfiguracja
- Zmienne środowiskowe:
  - `API_KEY`, `API_SECRET` – klucze PrimeXBT (nie są logowane wprost)
  - `CONFIRM=YES` – wymagane do uruchomienia live
  - `USE_TESTNET=true|false` – jeśli PrimeXBT udostępnia testnet
  - `MAX_LEVERAGE=5` – domyślny limit dźwigni
  - `REQUIRE_STOP_LOSS_LIVE=true|false` – domyślnie wymagany SL w live
  - `SUPABASE_DB_URL` – pełny URL do instancji Supabase Postgres (wymagany w środowisku produkcyjnym)
  - `DATABASE_URL` – alternatywna zmienna (np. dla innych baz), używana tylko jeśli `SUPABASE_DB_URL` nie jest ustawione
  - `ALLOW_SQLITE_FALLBACK=1` – wyłącznie dla lokalnych testów; pozwala użyć `sqlite:///trading.db` zamiast Supabase

### Integracja z PrimeXBT – checklist (do uzupełnienia)
- [ ] Uzupełnij endpointy w `bot/http/primexbt_client.py` zgodnie z oficjalną dokumentacją PrimeXBT
- [ ] Dodaj podpisywanie żądań, timestamp/nonce, limitowanie, retry
- [ ] Zaimplementuj mapowanie symboli i instrumentów
- [ ] Zweryfikuj TIF, reduce-only, dźwignię, SL/TP według zasad giełdy
- [ ] (Opcjonalnie) Testnet/sandbox, jeśli dostępny

W tym repo nie ma linków do nieoficjalnych źródeł. Wstaw oficjalne odnośniki, gdy będą dostępne (lub jeśli już je posiadasz).

### Bezpieczeństwo i ostrzeżenie
- Bot nie podejmuje autonomicznych decyzji – wykonuje wyłącznie jawne polecenia użytkownika.
- Handel lewarowany jest bardzo ryzykowny – istnieje wysokie prawdopodobieństwo utraty środków.

### Licencja
MIT


