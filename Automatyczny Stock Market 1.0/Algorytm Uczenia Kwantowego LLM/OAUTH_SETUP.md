# OAuth Setup Guide - Instrukcje logowania przez OAuth

## 📋 Przegląd

System obsługuje logowanie OAuth dla następujących giełd:
- **Binance** - Wymaga uzyskania Partner Program access 
- **Bybit** - Wymaga uzyskania Broker API access

## 🔧 Setup dla Binance OAuth

### Krok 1: Aplikacja do Partner Program
1. Idź do [Binance Partner Portal](https://partner.binance.com/)
2. Zarejestruj się jako partner technologiczny
3. Wypełnij wniosek o dostęp do API OAuth
4. Czekaj na zatwierdzenie (może potrwać kilka tygodni)

### Krok 2: Otrzymanie Credentials
Po zatwierdzeniu otrzymasz:
- `BINANCE_CLIENT_ID` 
- `BINANCE_CLIENT_SECRET`

### Krok 3: Konfiguracja Redirect URI
W panelu partnera ustaw:
```
http://localhost:8010/api/exchanges/oauth/callback/binance
```

## 🔧 Setup dla Bybit OAuth

### Krok 1: Aplikacja do Broker API
1. Idź do [Bybit Institutional](https://www.bybit.com/institutional/)
2. Skontaktuj się z zespołem Bybit w sprawie Broker API
3. Wypełnij dokumenty partnerskie
4. Czekaj na zatwierdzenie

### Krok 2: Otrzymanie Credentials  
Po zatwierdzeniu otrzymasz:
- `BYBIT_CLIENT_ID`
- `BYBIT_CLIENT_SECRET`

### Krok 3: Konfiguracja Redirect URI
W panelu brokera ustaw:
```
http://localhost:8010/api/exchanges/oauth/callback/bybit
```

## ⚙️ Konfiguracja w aplikacji

1. Skopiuj plik `env.example` do `.env`
2. Wypełnij otrzymane credentials:

```bash
# Binance OAuth
BINANCE_CLIENT_ID=your_real_binance_client_id
BINANCE_CLIENT_SECRET=your_real_binance_client_secret

# Bybit OAuth  
BYBIT_CLIENT_ID=your_real_bybit_client_id
BYBIT_CLIENT_SECRET=your_real_bybit_client_secret

# Base URL (dostosuj do deployment)
BASE_URL=http://localhost:8010
```

3. Uruchom ponownie aplikację

## 🎯 Jak używać OAuth

1. Idź do `/exchanges` w aplikacji
2. Kliknij "Connect via OAuth" przy wybranej giełdzie
3. Zostaniesz przekierowany na stronę autoryzacji giełdy
4. Zaloguj się i zatwierdź uprawnienia
5. Zostaniesz przekierowany z powrotem do aplikacji
6. Połączenie będzie aktywne!

## ⚠️ Ważne uwagi

### Security
- OAuth tokens są szyfrowane w bazie danych
- Tokens automatycznie się odnawiają
- Możesz odwołać dostęp w panelu giełdy

### Produkcja
- Zmień `BASE_URL` na prawdziwy adres serwera
- Ustaw HTTPS dla bezpieczeństwa
- Skonfiguruj właściwe redirect URI

### Demo Mode
- Aplikacja ma demo credentials dla testów
- Demo nie łączy się z prawdziwymi giełdami
- Służy do prezentacji interfejsu

## 🔄 Alternatywa - API Keys

Jeśli nie masz dostępu OAuth, nadal możesz używać tradycyjnych API keys:

1. Wygeneruj API keys w panelu giełdy
2. Użyj "Connect via API Key" w aplikacji
3. Wprowadź klucze ręcznie

## 📞 Pomoc

W przypadku problemów:
1. Sprawdź logi aplikacji
2. Zweryfikuj redirect URI
3. Upewnij się że credentials są poprawne
4. Skontaktuj się z supportem giełdy
