# 🎯 PRZYPISANIE KLUCZA API DO KONTA SUPABASE

## 📋 INFORMACJE O KONCIE

### Konto w Supabase Auth (`auth.users`)
```
✅ UUID: 3126f9fe-e724-4a33-bf4a-096804d56ece
✅ Email: olofilip16@gmail.com
✅ Username: filipsliwa
✅ Full Name: Filip Sliwa
✅ Utworzone: 2025-10-16 18:26:39
✅ Ostatnie logowanie: 2025-10-17 04:06:03
✅ Email potwierdzony: ✅ Tak (2025-10-16 18:27:02)
✅ Phone: +48518815055 (w public.profiles)
```

### Subskrypcja
```
Plan: Free
Status: Inactive
Trial: Nie rozpoczęty
```

---

## 🔑 PRZYPISANY KLUCZ API BINANCE

```
ID: 61a15889-155e-4d33-8405-841262aa68c7
User ID: 3126f9fe-e724-4a33-bf4a-096804d56ece
Exchange: binance
Testnet: ❌ FALSE (PRODUKCJA - LIVE TRADING)
Status: ✅ ACTIVE
Utworzony: 2025-10-18 01:53:24

API Key: Msr0cE4b...9DbtXEla (zaszyfrowany)
Secret Key: rjrTCVMq...74JsnZmH (zaszyfrowany)
```

---

## 📊 DANE WIDOCZNE W PANELU

### Portfolio Summary (`/api/portfolio/summary`)
```json
{
  "total_balance": 0.14,
  "total_pnl": 0.0,
  "total_pnl_percentage": 0.0,
  "available_balance": 0.14,
  "margin_used": 0.0,
  "free_margin": 0.14
}
```

### Pozycje w Portfolio (`public.portfolios`)
1. **USDT**: 0.13827 ($0.14)
2. **TON**: 0.00014265 ($0.00)
3. **SCR**: 0.00353725 ($0.00)

### Trading Settings (`public.trading_settings`)
```
Exchange: binance
Max Position Size: $1,000
Max Daily Loss: $100
Risk Level: 2/5 (Conservative)
Trading Enabled: ❌ FALSE (manual only)
Preferred Pairs: BTC/USDT, ETH/USDT
```

---

## 🔐 JAK ZALOGOWAĆ SIĘ DO PANELU

### Metoda 1: Web App (Frontend)
1. Otwórz aplikację webapp
2. Kliknij "Login"
3. Wprowadź dane:
   - **Email**: `olofilip16@gmail.com`
   - **Hasło**: `Milik112` (lub inne ustawione)

### Metoda 2: API Direct
```bash
curl -X POST http://185.70.198.201:8008/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "filipsliwa",
    "password": "Milik112"
  }'
```

Otrzymasz JWT token:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Użyj tokenu do API:
```bash
curl -X GET http://185.70.198.201:8008/api/portfolio/summary \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## 📍 GDZIE ZNALEŹĆ W SUPABASE DASHBOARD

### Krok 1: Otwórz Supabase
```
URL: https://supabase.com/dashboard
Projekt: iqqmbzznwpheqiihnjhz
```

### Krok 2: Authentication > Users
Szukaj użytkownika:
- **UUID**: `3126f9fe-e724-4a33-bf4a-096804d56ece`
- **Email**: `olofilip16@gmail.com`
- **Username**: `filipsliwa` (w metadata)

### Krok 3: Table Editor > public.profiles
```sql
SELECT * FROM public.profiles 
WHERE user_id = '3126f9fe-e724-4a33-bf4a-096804d56ece';
```

### Krok 4: Table Editor > public.api_keys
```sql
SELECT 
  id,
  exchange,
  is_active,
  is_testnet,
  created_at
FROM public.api_keys 
WHERE user_id = '3126f9fe-e724-4a33-bf4a-096804d56ece';
```

---

## 🔄 SYNCHRONIZACJA DANYCH Z BINANCE

### Wykonana synchronizacja:
✅ Portfolio positions → `public.portfolios`
✅ Portfolio snapshot → `public.portfolio_snapshots`
✅ Trading settings → `public.trading_settings`
✅ API keys → `public.api_keys` (zaszyfrowane)

### Skrypt synchronizacji:
```bash
/home/admin/asebot-backend/sync_binance_to_db.py
```

### Automatyzacja (opcjonalnie):
```bash
# Cron job - co 5 minut
*/5 * * * * cd /home/admin/asebot-backend && \
  source 'Algorytm Uczenia Kwantowego LLM/.venv/bin/activate' && \
  python sync_binance_to_db.py >> /var/log/binance_sync.log 2>&1
```

---

## ✅ WERYFIKACJA

### Test 1: Logowanie
```bash
curl -X POST http://185.70.198.201:8008/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"filipsliwa","password":"Milik112"}'
```
**Oczekiwany wynik**: JWT token

### Test 2: Portfolio
```bash
# Po otrzymaniu tokenu:
curl -X GET http://185.70.198.201:8008/api/portfolio/summary \
  -H "Authorization: Bearer YOUR_TOKEN"
```
**Oczekiwany wynik**: `total_balance: 0.14`

### Test 3: Risk Metrics
```bash
curl -X GET http://185.70.198.201:8008/api/portfolio/risk-metrics \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 🎉 PODSUMOWANIE

| Element | Status | Wartość |
|---------|--------|---------|
| Konto Supabase Auth | ✅ Aktywne | olofilip16@gmail.com |
| Profil w DB | ✅ Utworzony | UUID: 3126f9... |
| Klucz API Binance | ✅ Przypisany | Exchange: binance |
| Dane z Binance | ✅ Zsynchronizowane | $0.14 USDT |
| Webapp API | ✅ Działa | Port 8008 |
| Trading Bot | ✅ Gotowy | Port 8010-8011 |

**Wszystkie dane z Binance są teraz widoczne w panelu użytkownika `filipsliwa`** ✅
