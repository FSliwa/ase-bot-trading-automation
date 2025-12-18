# 🚀 Przewodnik Wdrożenia SPOT Constraints

**Data**: 21 października 2025  
**Szacowany czas**: 15-30 minut  
**Poziom ryzyka**: Średni (zalecany backup)

---

## 📋 Pre-requisites

### ✅ Checklist przed wdrożeniem:

- [ ] Masz dostęp do Supabase Dashboard
- [ ] Masz uprawnienia do wykonywania SQL (Database → SQL Editor)
- [ ] Wykonałeś backup bazy danych
- [ ] Przeczytałeś cały przewodnik
- [ ] System jest w trybie maintenance (opcjonalnie)

---

## 🔧 Krok 1: Backup Bazy Danych

### Opcja A: Supabase Dashboard
```
1. Przejdź do: Supabase Dashboard → Project → Settings → Database
2. Kliknij: "Backup & Restore"
3. Kliknij: "Create Manual Backup"
4. Poczekaj na potwierdzenie
```

### Opcja B: pg_dump (zaawansowane)
```bash
# Z lokalnej maszyny
pg_dump "postgresql://postgres:MIlik112%21%404%40@db.iqqmbzznwpheqiihnjhz.supabase.co:5432/postgres?sslmode=require" \
  -f "backup_before_spot_migration_$(date +%Y%m%d_%H%M%S).sql"
```

---

## 🚀 Krok 2: Uruchomienie Migracji

### 1. Otwórz Supabase SQL Editor
```
Supabase Dashboard → SQL Editor → New Query
```

### 2. Skopiuj i wklej skrypt
```
Otwórz plik: migrations/spot_constraints_migration.sql
Zaznacz całość (Ctrl+A)
Kopiuj (Ctrl+C)
Wklej do SQL Editor
```

### 3. Wykonaj migrację
```
Kliknij: "Run" (lub Ctrl+Enter)
Poczekaj na wykonanie (30-60 sekund)
```

### 4. Sprawdź wyniki testów
```
Przewiń do końca outputu
Sprawdź 6 testów weryfikacyjnych:
  - Test 1: Binance users trading_type ✅
  - Test 2: Binance API keys ✅
  - Test 3: Schema verification ✅
  - Test 4: Triggers verification ✅
  - Test 5: Audit log table ✅
  - Test 6: Views verification ✅
```

**Oczekiwane wyniki**:
- Test 1: `binance_users` > 0, `spot_users` = `binance_users`
- Test 2: `total_keys` > 0, `spot_only_keys` = `total_keys`
- Test 3: `new_columns_count` = 6
- Test 4: `triggers_count` = 2
- Test 5: `table_exists` = 1
- Test 6: `views_count` = 2

---

## ✅ Krok 3: Weryfikacja Manualna

### Sprawdź trading_settings
```sql
SELECT user_id, exchange::text, trading_type 
FROM public.trading_settings 
WHERE exchange::text = 'binance';
```
**Oczekiwany wynik**: Wszystkie Binance users mają `trading_type = 'spot'`

### Sprawdź api_keys
```sql
SELECT user_id, exchange::text, allowed_trading_types 
FROM public.api_keys 
WHERE exchange::text = 'binance';
```
**Oczekiwany wynik**: Wszystkie Binance keys mają `allowed_trading_types = {spot}`

### Test constraint na orders
```sql
-- Ten INSERT powinien ZADZIAŁAĆ (leverage automatycznie zmieniony na 1.0)
INSERT INTO public.orders (
  user_id, 
  client_order_id,
  exchange, 
  symbol, 
  side, 
  order_type, 
  quantity, 
  trading_type, 
  leverage
)
VALUES (
  '3126f9fe-e724-4a33-bf4a-096804d56ece', 
  'test_order_' || gen_random_uuid()::text,
  'binance', 
  'BTC/USDT', 
  'buy', 
  'limit', 
  0.001, 
  'margin',  -- próba użycia margin
  5.0        -- próba użycia leverage
);

-- Sprawdź wynik (leverage powinien być 1.0, trading_type = 'spot')
SELECT 
  client_order_id,
  exchange,
  trading_type,
  leverage,
  created_at
FROM public.orders 
WHERE user_id = '3126f9fe-e724-4a33-bf4a-096804d56ece'
ORDER BY created_at DESC 
LIMIT 1;

-- Usuń testowe zlecenie
DELETE FROM public.orders 
WHERE client_order_id LIKE 'test_order_%';
```

### Test constraint na positions (powinien RZUCIĆ BŁĄD)
```sql
-- Ten INSERT powinien RZUCIĆ EXCEPTION
INSERT INTO public.positions (
  user_id,
  exchange,
  strategy,
  symbol,
  side,
  quantity,
  entry_price,
  trading_type,
  leverage
)
VALUES (
  '3126f9fe-e724-4a33-bf4a-096804d56ece',
  'bybit',  -- nie Binance (Binance automatycznie zmienia)
  'test',
  'BTC/USDT',
  'long',
  0.001,
  50000.0,
  'spot',
  5.0  -- SPOT z leverage > 1.0 = ERROR
);

-- Oczekiwany błąd:
-- ERROR: SPOT positions cannot use leverage. Got leverage=5, expected 1.0
```

---

## 🔄 Krok 4: Restart Serwisu (jeśli wdrażasz od razu)

### Jeśli backend już działa:
```bash
# SSH do serwera
ssh admin@185.70.198.201

# Restart serwisu
sudo systemctl restart asebot.service

# Sprawdź status
systemctl status asebot.service

# Monitor logów
journalctl -u asebot.service -f
```

### Jeśli backend nie jest jeszcze zaktualizowany:
```
⚠️ NIE restartuj jeszcze serwisu!
Najpierw zaktualizuj kod Python (LiveBroker, AutoTradingEngine)
Zobacz: SUPABASE_SCHEMA_ANALYSIS.md sekcja "Zmiany w kodzie Python"
```

---

## ⚠️ Troubleshooting

### Problem: "relation already exists"
```
Rozwiązanie: Niektóre elementy już istnieją (OK, kontynuuj)
Skrypt używa "IF NOT EXISTS" więc jest idempotentny
```

### Problem: "constraint violation"
```
Rozwiązanie: Masz istniejące dane naruszające constraint
1. Sprawdź dane: SELECT * FROM orders WHERE trading_type = 'spot' AND leverage != 1.0;
2. Napraw dane: UPDATE orders SET leverage = 1.0 WHERE trading_type = 'spot';
3. Uruchom migrację ponownie
```

### Problem: "foreign key violation"
```
Rozwiązanie: Brak referencji w ai_analyses
1. Usuń constraint: ALTER TABLE trading_signals DROP CONSTRAINT IF EXISTS trading_signals_claude_analysis_id_fkey;
2. Migracja zrobi to automatycznie
```

### Problem: "type does not exist"
```
Rozwiązanie: Exchange type konflikt
1. Zamień exchange::text w skrypcie na CAST(exchange AS text)
2. Lub usuń ::text (Supabase powinien obsłużyć automatycznie)
```

---

## 🔙 Rollback (w razie problemów)

### Jeśli coś poszło nie tak:

```
1. Otwórz: migrations/rollback_spot_constraints.sql
2. Skopiuj do SQL Editor
3. Kliknij: "Run"
4. Sprawdź testy weryfikacyjne
5. Restart serwisu: sudo systemctl restart asebot.service
```

### Po rollback:
- Baza danych przywrócona do stanu sprzed migracji
- Wszystkie nowe kolumny usunięte
- Wszystkie triggery/constraints usunięte
- Możesz naprawić błędy i spróbować ponownie

---

## ✅ Post-Deployment Checklist

### Bezpośrednio po migracji:
- [ ] Wszystkie 6 testów weryfikacyjnych przeszły ✅
- [ ] Test INSERT na orders działa (trigger zmienia leverage)
- [ ] Test INSERT na positions rzuca błąd (constraint działa)
- [ ] Binance users mają trading_type = 'spot'
- [ ] Binance API keys mają allowed_trading_types = {spot}

### W ciągu 24h po wdrożeniu:
- [ ] Monitor audit log: `SELECT * FROM trading_type_audit_log ORDER BY created_at DESC LIMIT 100;`
- [ ] Sprawdź logi serwisu: `journalctl -u asebot.service --since "1 hour ago"`
- [ ] Sprawdź nowe orders: `SELECT * FROM orders WHERE created_at > now() - interval '24 hours';`
- [ ] Sprawdź trading_signals: `SELECT COUNT(*), trading_type FROM trading_signals WHERE created_at > now() - interval '24 hours' GROUP BY trading_type;`
- [ ] Zero critical errors w logach

### W ciągu 7 dni:
- [ ] Analiza audit log (ile prób naruszenia SPOT)
- [ ] Analiza performance (czy triggery spowalniają INSERTy)
- [ ] User feedback (czy są skargi na blokady zleceń)
- [ ] Dokumentacja zaktualizowana (API docs, user guide)

---

## 📊 Monitoring Queries

### Top 10 naruszeń SPOT constraints (ostatnie 7 dni)
```sql
SELECT 
  user_id,
  exchange,
  action_type,
  COUNT(*) as violations,
  MAX(created_at) as last_violation
FROM trading_type_audit_log
WHERE created_at > now() - interval '7 days'
GROUP BY user_id, exchange, action_type
ORDER BY violations DESC
LIMIT 10;
```

### Statystyki SPOT trading per user
```sql
SELECT * FROM user_spot_trading_stats
ORDER BY total_spot_volume DESC
LIMIT 20;
```

### Aktywne sygnały SPOT vs MARGIN/FUTURES
```sql
SELECT 
  trading_type,
  COUNT(*) as active_signals,
  AVG(confidence_score) as avg_confidence
FROM trading_signals
WHERE is_active = true
  AND (expires_at IS NULL OR expires_at > now())
GROUP BY trading_type;
```

### Orders z automatycznie zmienionym leverage (przez trigger)
```sql
-- Te orders miały leverage > 1.0 ale trigger zmienił na 1.0
SELECT 
  client_order_id,
  exchange,
  symbol,
  leverage,
  created_at
FROM orders
WHERE exchange = 'binance'
  AND trading_type = 'spot'
  AND created_at > now() - interval '24 hours'
ORDER BY created_at DESC;
```

---

## 🎯 Success Criteria

### Migracja uznana za udaną jeśli:

✅ **Poziom 1: Technical**
- Wszystkie testy weryfikacyjne przeszły (6/6)
- Triggery aktywne (enforce_spot_trading, enforce_spot_position)
- Constraints aktywne (3 constraints)
- Zero critical errors w logach

✅ **Poziom 2: Functional**
- Binance users nie mogą tworzyć orders z leverage > 1.0
- AI insights zawierają exchange i trading_type
- Trading signals linkują do Claude analysis
- Audit log zapisuje próby naruszenia

✅ **Poziom 3: Business**
- Zero financial losses z powodu nieprawidłowych zleceń
- User satisfaction: zero skarg na blokady (po wyjaśnieniu SPOT-only)
- Compliance: 100% Binance trades to SPOT (audit log)
- Performance: < 5ms overhead na INSERT (trigger execution time)

---

## 📞 Support

### W razie pytań lub problemów:

1. **Sprawdź logi**: `journalctl -u asebot.service -n 100`
2. **Sprawdź audit**: `SELECT * FROM trading_type_audit_log ORDER BY created_at DESC LIMIT 50;`
3. **Rollback**: Użyj `rollback_spot_constraints.sql` jeśli krytyczny problem
4. **Kontakt**: Zgłoś issue z:
   - Output testów weryfikacyjnych
   - Error messages
   - Logs excerpt (last 100 lines)

---

## 📚 Dodatkowa Dokumentacja

- **Analiza schematu**: `SUPABASE_SCHEMA_ANALYSIS.md`
- **Kod Python**: Sekcja "Zmiany w kodzie Python" w SUPABASE_SCHEMA_ANALYSIS.md
- **API keys i konta**: `API_KEYS_AND_ACCOUNTS_ANALYSIS.md`
- **SPOT constraints**: `EXCHANGE_SPOT_CONSTRAINTS.md`

---

**Powodzenia! 🚀**

*Jeśli wszystko poszło dobrze, powinieneś zobaczyć komunikat:*
```
✅ SPOT Constraints Migration - ZAKOŃCZONA
```
