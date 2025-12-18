### Założenia i ograniczenia (MVP PrimeXBT Trading Bot)

- **Zakres API i warstwa adaptacyjna**
  - **API PrimeXBT**: zakładamy dostępność wyłącznie do zleceń tradingowych (bez wypłat) i konieczność użycia klucza i sekretu API.
  - **Niepełna dokumentacja**: jeśli oficjalne API nie jest w pełni udokumentowane publicznie, projekt zawiera warstwę adaptacyjną z metodami-wypełniaczami (NotImplementedError), aby nie zgadywać nieznanych endpointów.
  - **Integracja live**: uzupełnienie metod warstwy HTTP zgodnie z oficjalną dokumentacją PrimeXBT jest wymagane przed użyciem trybu live; w `README` znajduje się checklistą integracyjna z odnośnikami do dokumentacji.

- **Bezpieczeństwo i konfiguracja**
  - **Brak loginu/hasła i scrapingu UI**: jedynym sposobem autoryzacji są klucze API.
  - **Brak sekretów w repozytorium**: klucze API nie są nigdzie zapisywane na stałe; użytkownik podaje je przez zmienne środowiskowe lub plik `.env`. Dostarczony jest szablon `.env.example`.
  - **Sanityzacja logów**: logi nie zawierają jawnie kluczy ani sekretów.
  - **Domyślny tryb**: paper trading (symulacja bez użycia prawdziwych środków).

- **Bramka bezpieczeństwa i uruchamianie trybu live**
  - **Wymagana świadoma zgoda**: aby włączyć tryb rzeczywisty, należy uruchomić z `--live` oraz potwierdzić chęć uruchomienia ustawiając `CONFIRM=YES` lub przekazując `--confirm-yes`.
  - **Ochrona przed pomyłką**: bez tej zgody prawdziwe zlecenia nie zostaną wysłane.

- **Parser poleceń tradingowych (LLM `parse_trade_intent`)**
  - **Implementacja regułowa**: parser oparty na prostych regułach (słownik + wyrażenia regularne), a nie pełnej inteligencji LLM.
  - **Obsługiwane komendy**: typowe polecenia po polsku i angielsku, np. „kup 0.01 BTCUSDT limit 60000 SL 58500 TP 61500 lev 3x”.
  - **Ograniczenia**: nie obsługuje wszystkich wariantów językowych/semantycznych.

- **Instrumenty i symbole**
  - **Zakres**: podstawowe pary walutowe (np. `BTCUSDT`, `ETHUSD`).
  - **Walidacja**: sprawdzamy jedynie, czy symbol jest podany i sformatowany wielkimi literami.
  - **Brak weryfikacji dostępności**: brak wbudowanej oficjalnej listy instrumentów; zakładamy dostępność podanego symbolu (opcjonalnie można dodać listę obsługiwanych symboli).

- **Testnet i paper trading**
  - **Testnet (jeśli dostępny)**: opcjonalny `use_testnet` w konfiguracji, jeśli PrimeXBT oferuje sandbox/testnet.
  - **Bezpieczny tryb w MVP**: realizowany głównie przez `paper_trading=True` z wbudowanym symulatorem (`PaperBroker`).
  - **Brak trwałości stanu**: paper trading nie zachowuje stanu między restartami (dane w pamięci procesu). Polecenie `trade` i późniejsze `status` w osobnych procesach CLI mogą nie widzieć wspólnego stanu.
  - **Kierunek docelowy**: do utrzymania stanu w produkcie zaleca się bazę danych lub persistent service.

- **Operacje na koncie i integracja live**
  - **Brak realnych zleceń bez zgody**: żadne rzeczywiste zlecenie nie jest wysyłane do PrimeXBT, dopóki użytkownik nie włączy trybu live i nie potwierdzi.
  - **Klient HTTP**: w trybie live używana byłaby klasa `PrimeXbtHttpClient`; obecnie metody rzucają `NotImplementedError` z informacją o konieczności implementacji wg dokumentacji API.

- **Obsługiwane funkcje tradingowe**
  - **Typy zleceń**: market i limit.
  - **Parametry**: TIF (`GTC`/`IOC`/`FOK`), `stop-loss`, `take-profit`, znacznik `reduce-only` (redukcja pozycji), oraz lewarowanie (domyślnie ograniczone do `5x`, konfigurowalne).
  - **Zamykanie pozycji**: komenda `close_position` dla danego instrumentu.
  - **Poza zakresem MVP**: OCO, trailing stop (możliwe do dodania w przyszłości).

- **Zarządzanie ryzykiem**
  - **Wymagany stop-loss**: dla nowych pozycji (można wyłączyć w konfiguracji).
  - **Egzekucja**: brak `stop-loss` skutkuje odrzuceniem zlecenia w trybie live.

- **Zgodność z regulacjami i TOS**
  - **Brak autonomii inwestycyjnej**: bot nie podejmuje samodzielnych decyzji; wykonuje wyłącznie jawne polecenia użytkownika (ewentualnie prosząc o potwierdzenie).
  - **Ostrzeżenie o ryzyku**: handel lewarowany jest bardzo ryzykowny i może prowadzić do szybkiej utraty środków.

- **Konfiguracja i uruchamianie**
  - **Zmienne środowiskowe**: `API_KEY`, `API_SECRET`, `CONFIRM=YES` (do potwierdzenia live), ewentualnie `USE_TESTNET`.
  - **Pliki konfiguracyjne**: `.env` na bazie szablonu `.env.example`.
  - **Flagi CLI**: `--live` (włączenie trybu rzeczywistego), `--confirm-yes` (potwierdzenie uruchomienia live).
  - **Limity i reguły**: maks. dźwignia domyślnie `5x` (konfigurowalne), wymaganie `stop-loss` (konfigurowalne).

- **Dokumentacja i checklisty**
  - **README**: zawiera checklistę integracyjną z odnośnikami do oficjalnej dokumentacji PrimeXBT niezbędną do uzupełnienia metod warstwy HTTP przed uruchomieniem live.


