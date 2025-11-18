## Automatyczny Bot Tradingowy (v1.0)
wny kod na strone
aplikacji)

### 🤖 W pełni automatyczny trading z AI (GPT-5 Pro)

Bot tradingowy działający całkowicie automatycznie - analizuje rynki, podejmuje decyzje i wykonuje transakcje bez interwencji użytkownika.

## 🚀 SZYBKI START - AUTOMATYCZNY BOT

### Jeden krok do uruchomienia:
```bash
./run_auto_bot.sh
```

### Panel kontrolny z pełnym podglądem:
Po uruchomieniu bota, otwórz w przeglądarce:
```
http://localhost:8010
```

Dashboard zawiera wszystkie niezbędne parametry:
- 💰 **Stan konta** - balans, margin, PnL w czasie rzeczywistym  
- 📈 **Otwarte pozycje** - szczegóły każdej pozycji z ceną likwidacji
- ⚠️ **Metryki ryzyka** - drawdown, risk of ruin, circuit breakers
- 📊 **Performance** - win rate, profit factor, Sharpe ratio
- 🧠 **Analiza AI** - rekomendacje GPT-5 Pro, sentyment rynku
- 🎯 **Aktywne strategie** - status i skuteczność strategii
- 📜 **Historia transakcji** - pełna historia z PnL
- ⚡ **Szybkie akcje** - emergency stop, close all, pause trading

Bot automatycznie:
- ✅ Analizuje rynki co minutę używając AI (GPT-5 Pro)
- ✅ Wykonuje transakcje na podstawie strategii (Momentum, Mean Reversion)
- ✅ Zarządza ryzykiem (stop loss, take profit, limity pozycji)
- ✅ Działa 24/7 bez nadzoru
- ✅ Loguje wszystkie operacje do bazy danych

# 🚀 AI Trading Bot - Zaawansowany System Tradingowy z AI

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116.1-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](Dockerfile)

## 📋 Opis Projektu

Profesjonalny system tradingowy z wykorzystaniem sztucznej inteligencji, oferujący:

- 🤖 **AI-driven trading** z integracją OpenAI, Google Gemini, Anthropic
- 📊 **Zaawansowana analiza techniczna** i sentiment analysis
- 🔒 **Bezpieczne zarządzanie kontami** z JWT i MFA
- 📈 **Real-time monitoring** i metryki
- 🌐 **Modern web interface** z React-like components
- 🔌 **Multi-exchange support** (Binance, PrimeXBT, itp.)

## 🗂️ Używane Porty

| Port | Usługa | Opis |
|------|--------|------|
| **8000** | FastAPI | Główne API aplikacji |
| **8008** | Web App | Frontend aplikacji |
| **8080** | Alternative | Backup/development port |
| **3000** | Node.js | Frontend development server |
| **5432** | PostgreSQL | Baza danych (localhost) |
| **6379** | Redis | Cache i session storage |
| **80** | Nginx | HTTP reverse proxy |
| **443** | Nginx | HTTPS (SSL) |
| **22** | SSH | Dostęp zdalny |
| **9090** | Prometheus | Metryki (localhost) |

## 🚀 Quick Start

### Lokalne uruchomienie

```bash
# Klonuj repozytorium
git clone https://github.com/[username]/ai-trading-bot.git
cd ai-trading-bot

# Utwórz environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# lub venv\Scripts\activate  # Windows

## Instalacja

1. **Instalacja dependencies:**
```bash
pip install -r requirements.txt
```

2. **Konfiguracja:**
```bash
cp env.example .env
# Edytuj .env file

### Szybki start
1) Utwórz i aktywuj środowisko (z katalogu projektu):
```
python3 -m venv .venv
source .venv/bin/activate
```

2) Zainstaluj zależności:
```
pip install -r requirements.txt
```

3) Skonfiguruj `.env` na bazie `env.example` (opcjonalne dla paper trading):
```
cp .env.example .env
```

4) Uruchom pomoc CLI:
```
python -m bot.cli --help
```

### UI (FastAPI)
Uruchom UI (domyślnie na `http://127.0.0.1:8008`):
```
python -m uvicorn web.app:app --host 127.0.0.1 --port 8008
```

Dashboard udostępnia:
- Formularz trade (paper)
- Podgląd pozycji i filli
- Akcje: close-position, close-all

API pomocnicze:
```
GET /api/status
GET /api/fills
```

### Użycie (paper trading – domyślnie)
Przykładowe polecenie (PL):
```
python -m bot.cli trade "kup 0.01 BTCUSDT limit 60000 SL 58500 TP 61500 lev 3x"
```

Przykładowe polecenie (EN):
```
python -m bot.cli trade "buy 0.01 BTCUSDT market SL 58500 TP 61500 lev 3x" --price 60250
```

Status pozycji (paper):
```
python -m bot.cli status
```

Zamknięcie pozycji:
```
python -m bot.cli close-position BTCUSDT
```

#### Utrzymywanie stanu paper (opcjonalnie)
Możesz utrwalając stan między wywołaniami procesu:
```
python -m bot.cli trade "buy 0.05 BTCUSDT market SL 58000 lev 2x" --price 59000 --persist --state-file state.json
python -m bot.cli status --persist --state-file state.json
python -m bot.cli close-position BTCUSDT --persist --state-file state.json
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

### Konfiguracja
- Zmienne środowiskowe:
  - `API_KEY`, `API_SECRET` – klucze PrimeXBT (nie są logowane wprost)
  - `CONFIRM=YES` – wymagane do uruchomienia live
  - `USE_TESTNET=true|false` – jeśli PrimeXBT udostępnia testnet
  - `MAX_LEVERAGE=5` – domyślny limit dźwigni
  - `REQUIRE_STOP_LOSS_LIVE=true|false` – domyślnie wymagany SL w live

### Integracja z PrimeXBT – checklist (do uzupełnienia)
- [ ] Uzupełnij endpointy w `bot/http/primexbt_client.py` zgodnie z oficjalną dokumentacją PrimeXBT.
- [ ] Dodaj podpisywanie żądań, timestamp/nonce, limitowanie, retry.
- [ ] Zaimplementuj mapowanie symboli i instrumentów.
- [ ] Zweryfikuj TIF, reduce-only, dźwignię, SL/TP według zasad giełdy.
- [ ] (Opcjonalnie) Testnet/sandbox, jeśli dostępny.

W tym repo nie ma linków do nieoficjalnych źródeł. Wstaw oficjalne odnośniki, gdy będą dostępne (lub jeśli już je posiadasz).

### Bezpieczeństwo i ostrzeżenie
- Bot nie podejmuje autonomicznych decyzji – wykonuje wyłącznie jawne polecenia użytkownika.
- Handel lewarowany jest bardzo ryzykowny – istnieje wysokie prawdopodobieństwo utraty środków.

### Licencja
MIT


