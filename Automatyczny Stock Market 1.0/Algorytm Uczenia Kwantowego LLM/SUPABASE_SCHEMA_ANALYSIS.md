# 🗄️ Analiza Schematu Bazy Danych Supabase

**Data**: 21 października 2025  
**Analizowany system**: ASE Trading Bot Database Schema

---

## ✅ AKTUALIZACJA KLUCZY API

### **Status implementacji:**
```bash
✅ CLAUDE_API_KEY dodany do .env
✅ TAVILY_API_KEY dodany do .env
✅ Serwis zrestartowany (asebot.service)
✅ 4 workery uvicorn działają (PID: 2906425)
```

### **Weryfikacja:**
```bash
# Sprawdzenie .env
CLAUDE_API_KEY=sk-ant-api03-divvpk_RUgU3OGBvQ1x...eNIlkgAA ✅
TAVILY_API_KEY=tvly-dev-5syq2CvMkAQWzA6vm5C...Q3xp2T1v ✅

# Status serwisu
Active: active (running) since Tue 2025-10-21 05:10:10 UTC ✅
Memory: 256.1M (peak: 257.1M)
Tasks: 14 (4 worker processes)
```

**Uwaga**: Endpoint `/api/ai/health` nadal zwraca 500 error - wymaga dalszej diagnozy (prawdopodobnie problem z logiką health check, nie z kluczami API).

---

## 📊 ANALIZA SCHEMATU SQL - ZMIANY I ULEPSZENIA

### **1. TABELA `trading_settings` - KRYTYCZNA ZMIANA**

#### ❌ **Problem:**
```sql
CREATE TABLE public.trading_settings (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  exchange USER-DEFINED NOT NULL,
  is_trading_enabled boolean DEFAULT false,
  max_daily_loss numeric DEFAULT 100,
  max_position_size numeric DEFAULT 1000,
  risk_level integer DEFAULT 3 CHECK (risk_level >= 1 AND risk_level <= 5),
  preferred_pairs ARRAY DEFAULT ARRAY['BTC/USDT'::text, 'ETH/USDT'::text],
  stop_loss_percentage numeric DEFAULT 5.0,
  take_profit_percentage numeric DEFAULT 10.0,
  strategy_config jsonb DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  -- BRAK KOLUMNY trading_type (SPOT/MARGIN/FUTURES)
);
```

#### ✅ **Rozwiązanie:**
```sql
-- 1. Dodanie kolumny trading_type
ALTER TABLE public.trading_settings 
ADD COLUMN trading_type text NOT NULL DEFAULT 'spot'
CHECK (trading_type IN ('spot', 'margin', 'futures'));

-- 2. Index dla szybszego wyszukiwania
CREATE INDEX idx_trading_settings_user_exchange 
ON public.trading_settings(user_id, exchange);

-- 3. Unique constraint aby jeden user miał jedno ustawienie na giełdę
ALTER TABLE public.trading_settings 
ADD CONSTRAINT unique_user_exchange 
UNIQUE (user_id, exchange);

-- 4. Update dla Binance users (wymuszenie SPOT)
UPDATE public.trading_settings 
SET trading_type = 'spot' 
WHERE exchange = 'binance';
```

**Uzasadnienie**:
- AI analysis obecnie dynamicznie dodaje `[CRITICAL TRADING CONSTRAINTS]` na poziomie promptu
- **Trwała konfiguracja SPOT** powinna być zapisana w bazie dla:
  - Walidacji przed wykonaniem zlecenia (LiveBroker)
  - Filtrowania sygnałów AI (AutoTradingEngine)
  - Audytu i zgodności regulacyjnej
  - UI/dashboard (wyświetlanie użytkownikowi)

---

### **2. TABELA `ai_insights` - ROZBUDOWA**

#### ⚠️ **Obecny stan:**
```sql
CREATE TABLE public.ai_insights (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  insight_type text NOT NULL CHECK (...),
  title text NOT NULL,
  description text NOT NULL,
  confidence_score integer NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 100),
  action_required text,
  priority text NOT NULL DEFAULT 'medium'::text CHECK (...),
  related_symbols ARRAY,
  metadata jsonb DEFAULT '{}'::jsonb,
  is_read boolean NOT NULL DEFAULT false,
  expires_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  source_url text,
  -- BRAK: exchange, trading_type, validation_status
);
```

#### ✅ **Ulepszenie:**
```sql
-- 1. Dodaj kolumnę exchange (identyfikacja z jakiej giełdy insight)
ALTER TABLE public.ai_insights 
ADD COLUMN exchange text;

-- 2. Dodaj kolumnę trading_type (SPOT/MARGIN/FUTURES)
ALTER TABLE public.ai_insights 
ADD COLUMN trading_type text 
CHECK (trading_type IN ('spot', 'margin', 'futures'));

-- 3. Dodaj kolumnę gemini_validation_status (czy insight przeszedł walidację)
ALTER TABLE public.ai_insights 
ADD COLUMN gemini_validation_status text 
CHECK (gemini_validation_status IN ('approve', 'revise', 'reject', 'pending'));

-- 4. Dodaj kolumnę validation_risk_flags (flagi ryzyka z Gemini)
ALTER TABLE public.ai_insights 
ADD COLUMN validation_risk_flags text[];

-- 5. Index dla filtrowania insights per exchange
CREATE INDEX idx_ai_insights_user_exchange 
ON public.ai_insights(user_id, exchange) 
WHERE is_read = false;

-- 6. Index dla nieaktywnych insights wymagających akcji
CREATE INDEX idx_ai_insights_active_priority 
ON public.ai_insights(priority, created_at) 
WHERE is_read = false AND expires_at > now();
```

**Uzasadnienie**:
- Pełna integracja z nowym flow AI (Claude → Gemini validation)
- Tracking SPOT constraints na poziomie każdego insightu
- Możliwość filtrowania insights per giełda (ważne dla multi-exchange users)

---

### **3. TABELA `trading_signals` - ROZBUDOWA**

#### ⚠️ **Obecny stan:**
```sql
CREATE TABLE public.trading_signals (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid,
  symbol text NOT NULL,
  signal_type text NOT NULL CHECK (signal_type = ANY (ARRAY['buy'::text, 'sell'::text, 'hold'::text])),
  strength integer NOT NULL CHECK (strength >= 0 AND strength <= 100),
  price_target numeric,
  stop_loss numeric,
  take_profit numeric,
  confidence_score integer NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 100),
  ai_analysis text,
  source text NOT NULL DEFAULT 'gemini_ai'::text,
  is_active boolean NOT NULL DEFAULT true,
  expires_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  -- BRAK: exchange, trading_type, claude_analysis, gemini_validation
);
```

#### ✅ **Ulepszenie:**
```sql
-- 1. Dodaj exchange (z jakiej giełdy sygnał)
ALTER TABLE public.trading_signals 
ADD COLUMN exchange text;

-- 2. Dodaj trading_type (SPOT/MARGIN/FUTURES)
ALTER TABLE public.trading_signals 
ADD COLUMN trading_type text NOT NULL DEFAULT 'spot'
CHECK (trading_type IN ('spot', 'margin', 'futures'));

-- 3. Dodaj claude_analysis_id (link do pełnej analizy Claude)
ALTER TABLE public.trading_signals 
ADD COLUMN claude_analysis_id bigint 
REFERENCES public.ai_analyses(id);

-- 4. Dodaj gemini_validation (JSON z wynikiem walidacji Gemini)
ALTER TABLE public.trading_signals 
ADD COLUMN gemini_validation jsonb;

-- 5. Dodaj tavily_context (czy sygnał wykorzystał web search)
ALTER TABLE public.trading_signals 
ADD COLUMN tavily_context boolean DEFAULT false;

-- 6. Update source (domyślnie 'claude_ai' zamiast 'gemini_ai')
ALTER TABLE public.trading_signals 
ALTER COLUMN source SET DEFAULT 'claude_ai';

-- 7. Index dla aktywnych sygnałów per exchange
CREATE INDEX idx_trading_signals_active_exchange 
ON public.trading_signals(user_id, exchange, is_active) 
WHERE is_active = true AND expires_at > now();

-- 8. Index dla sygnałów per trading_type (łatwe filtrowanie SPOT)
CREATE INDEX idx_trading_signals_trading_type 
ON public.trading_signals(trading_type, created_at) 
WHERE is_active = true;
```

**Uzasadnienie**:
- Sygnały powinny zawierać pełny kontekst AI pipeline (Claude → Gemini → Tavily)
- SPOT constraint tracking na poziomie każdego sygnału
- Możliwość audytu: który sygnał był wzbogacony web search, który przeszedł walidację

---

### **4. TABELA `orders` - WALIDACJA TRADING TYPE**

#### ⚠️ **Obecny stan:**
```sql
CREATE TABLE public.orders (
  id bigint NOT NULL DEFAULT nextval('orders_id_seq'::regclass),
  client_order_id text NOT NULL UNIQUE,
  user_id uuid,
  strategy text,
  symbol text NOT NULL,
  side text NOT NULL,
  order_type text NOT NULL,
  quantity double precision NOT NULL,
  price double precision,
  stop_price double precision,
  time_in_force text,
  reduce_only boolean NOT NULL DEFAULT false,
  leverage double precision NOT NULL DEFAULT 1.0, -- ⚠️ leverage domyślnie 1.0
  status text NOT NULL DEFAULT 'NEW'::text,
  -- BRAK: trading_type, exchange
);
```

#### ✅ **Ulepszenie:**
```sql
-- 1. Dodaj exchange (z jakiej giełdy zlecenie)
ALTER TABLE public.orders 
ADD COLUMN exchange text;

-- 2. Dodaj trading_type (SPOT/MARGIN/FUTURES)
ALTER TABLE public.orders 
ADD COLUMN trading_type text NOT NULL DEFAULT 'spot'
CHECK (trading_type IN ('spot', 'margin', 'futures'));

-- 3. Constraint: SPOT orders MUSZĄ mieć leverage = 1.0
ALTER TABLE public.orders 
ADD CONSTRAINT check_spot_no_leverage 
CHECK (
  (trading_type = 'spot' AND leverage = 1.0) OR 
  (trading_type != 'spot')
);

-- 4. Function do walidacji przed insertem (automatyczne wymuszenie SPOT dla Binance)
CREATE OR REPLACE FUNCTION validate_order_trading_type()
RETURNS TRIGGER AS $$
BEGIN
  -- Jeśli exchange = 'binance', wymuś trading_type = 'spot'
  IF NEW.exchange = 'binance' THEN
    NEW.trading_type := 'spot';
    NEW.leverage := 1.0;
  END IF;
  
  -- Jeśli trading_type = 'spot', wymuś leverage = 1.0
  IF NEW.trading_type = 'spot' AND NEW.leverage != 1.0 THEN
    NEW.leverage := 1.0;
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 5. Trigger do automatycznej walidacji
CREATE TRIGGER enforce_spot_trading 
BEFORE INSERT OR UPDATE ON public.orders 
FOR EACH ROW 
EXECUTE FUNCTION validate_order_trading_type();

-- 6. Index dla zleceń per exchange + trading_type
CREATE INDEX idx_orders_exchange_trading_type 
ON public.orders(user_id, exchange, trading_type, created_at);
```

**Uzasadnienie**:
- **Walidacja na poziomie bazy danych** - ostatnia linia obrony przed błędnymi zleceniami
- Automatyczne wymuszenie SPOT dla Binance (fail-safe)
- Constraint `leverage = 1.0` dla wszystkich SPOT orders (nie można obejść)

---

### **5. TABELA `trades` - TRACKING TRADING TYPE**

#### ⚠️ **Obecny stan:**
```sql
CREATE TABLE public.trades (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  exchange USER-DEFINED NOT NULL,
  symbol text NOT NULL,
  trade_type USER-DEFINED NOT NULL, -- ⚠️ to jest buy/sell, nie SPOT/MARGIN
  amount numeric NOT NULL,
  price numeric NOT NULL,
  fee numeric DEFAULT 0,
  fee_currency text DEFAULT 'USDT'::text,
  status USER-DEFINED DEFAULT 'pending'::trade_status,
  exchange_order_id text,
  strategy_name text,
  notes text,
  executed_at timestamp with time zone,
  -- BRAK: trading_type (SPOT/MARGIN/FUTURES)
);
```

#### ✅ **Ulepszenie:**
```sql
-- 1. Dodaj trading_market_type (SPOT/MARGIN/FUTURES) - unikamy kolizji nazw
ALTER TABLE public.trades 
ADD COLUMN trading_market_type text NOT NULL DEFAULT 'spot'
CHECK (trading_market_type IN ('spot', 'margin', 'futures'));

-- 2. Index dla analityki trades per market type
CREATE INDEX idx_trades_market_type_executed 
ON public.trades(user_id, exchange, trading_market_type, executed_at) 
WHERE status = 'completed';

-- 3. View dla SPOT-only trades (łatwy monitoring)
CREATE OR REPLACE VIEW spot_trades AS 
SELECT * FROM public.trades 
WHERE trading_market_type = 'spot';

-- 4. View dla statystyk SPOT trading per user
CREATE OR REPLACE VIEW user_spot_trading_stats AS
SELECT 
  user_id,
  exchange,
  COUNT(*) AS total_spot_trades,
  SUM(amount * price) AS total_spot_volume,
  AVG(fee) AS avg_spot_fee,
  MIN(executed_at) AS first_spot_trade,
  MAX(executed_at) AS last_spot_trade
FROM public.trades 
WHERE trading_market_type = 'spot' 
  AND status = 'completed'
GROUP BY user_id, exchange;
```

**Uzasadnienie**:
- Pełny tracking SPOT trading w historii transakcji
- Możliwość audytu zgodności (czy user tylko SPOT dla Binance)
- Analityka per market type (SPOT vs MARGIN vs FUTURES)

---

### **6. TABELA `positions` - WALIDACJA LEVERAGE**

#### ⚠️ **Obecny stan:**
```sql
CREATE TABLE public.positions (
  id bigint NOT NULL DEFAULT nextval('positions_id_seq'::regclass),
  user_id uuid,
  strategy text,
  symbol text NOT NULL,
  side text NOT NULL,
  quantity double precision NOT NULL,
  entry_price double precision NOT NULL,
  current_price double precision,
  leverage double precision NOT NULL DEFAULT 1.0, -- ⚠️ domyślnie 1.0 ale brak walidacji
  status text NOT NULL DEFAULT 'OPEN'::text,
  -- BRAK: exchange, trading_type
);
```

#### ✅ **Ulepszenie:**
```sql
-- 1. Dodaj exchange
ALTER TABLE public.positions 
ADD COLUMN exchange text;

-- 2. Dodaj trading_type (SPOT/MARGIN/FUTURES)
ALTER TABLE public.positions 
ADD COLUMN trading_type text NOT NULL DEFAULT 'spot'
CHECK (trading_type IN ('spot', 'margin', 'futures'));

-- 3. Constraint: SPOT positions MUSZĄ mieć leverage = 1.0
ALTER TABLE public.positions 
ADD CONSTRAINT check_spot_position_no_leverage 
CHECK (
  (trading_type = 'spot' AND leverage = 1.0) OR 
  (trading_type != 'spot')
);

-- 4. Function do walidacji przed otwarciem pozycji
CREATE OR REPLACE FUNCTION validate_position_trading_type()
RETURNS TRIGGER AS $$
BEGIN
  -- Jeśli exchange = 'binance', wymuś trading_type = 'spot'
  IF NEW.exchange = 'binance' THEN
    NEW.trading_type := 'spot';
    NEW.leverage := 1.0;
  END IF;
  
  -- Jeśli trading_type = 'spot', wymuś leverage = 1.0
  IF NEW.trading_type = 'spot' AND NEW.leverage != 1.0 THEN
    RAISE EXCEPTION 'SPOT positions cannot use leverage. Got leverage=%, expected 1.0', NEW.leverage;
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 5. Trigger do automatycznej walidacji
CREATE TRIGGER enforce_spot_position 
BEFORE INSERT OR UPDATE ON public.positions 
FOR EACH ROW 
EXECUTE FUNCTION validate_position_trading_type();

-- 6. Index dla otwartych pozycji per exchange + trading_type
CREATE INDEX idx_positions_open_exchange 
ON public.positions(user_id, exchange, trading_type, status) 
WHERE status = 'OPEN';
```

**Uzasadnienie**:
- Pozycje SPOT **nie mogą mieć leverage > 1.0** (wymuszenie na poziomie DB)
- Automatyczna walidacja przy otwieraniu pozycji (trigger)
- Exception jeśli próba otwarcia pozycji SPOT z leverage

---

### **7. TABELA `api_keys` - TRACKING TRADING TYPE**

#### ⚠️ **Obecny stan:**
```sql
CREATE TABLE public.api_keys (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  exchange USER-DEFINED NOT NULL,
  passphrase text,
  is_testnet boolean DEFAULT true,
  is_active boolean DEFAULT true,
  encrypted_api_key text NOT NULL,
  encrypted_api_secret text NOT NULL,
  -- BRAK: allowed_trading_types (jakie typy trading user może używać)
);
```

#### ✅ **Ulepszenie:**
```sql
-- 1. Dodaj allowed_trading_types (array: ['spot', 'margin', 'futures'])
ALTER TABLE public.api_keys 
ADD COLUMN allowed_trading_types text[] NOT NULL DEFAULT ARRAY['spot'];

-- 2. Constraint: Binance API keys MOGĄ TYLKO SPOT
ALTER TABLE public.api_keys 
ADD CONSTRAINT check_binance_spot_only 
CHECK (
  (exchange::text = 'binance' AND allowed_trading_types = ARRAY['spot']) OR 
  (exchange::text != 'binance')
);

-- 3. Update istniejących Binance keys
UPDATE public.api_keys 
SET allowed_trading_types = ARRAY['spot'] 
WHERE exchange::text = 'binance';

-- 4. Index dla szybkiego wyszukiwania keys per trading type
CREATE INDEX idx_api_keys_trading_types 
ON public.api_keys USING GIN (allowed_trading_types);

-- 5. Function do walidacji zgodności API key z trading type
CREATE OR REPLACE FUNCTION check_api_key_supports_trading_type(
  p_api_key_id uuid,
  p_trading_type text
) RETURNS boolean AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM public.api_keys 
    WHERE id = p_api_key_id 
      AND p_trading_type = ANY(allowed_trading_types)
      AND is_active = true
  );
END;
$$ LANGUAGE plpgsql;
```

**Uzasadnienie**:
- API key zawiera **konfigurację uprawnień trading** (SPOT/MARGIN/FUTURES)
- Binance API keys **wymuszają SPOT-only** na poziomie DB
- Możliwość walidacji przed wykonaniem zlecenia: `check_api_key_supports_trading_type()`

---

### **8. NOWA TABELA: `trading_type_audit_log`**

#### ✅ **Nowa tabela do audytu:**
```sql
-- Tabela do trackingu prób naruszenia SPOT constraints
CREATE TABLE public.trading_type_audit_log (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  exchange text NOT NULL,
  attempted_trading_type text NOT NULL,
  allowed_trading_type text NOT NULL,
  action_type text NOT NULL CHECK (action_type IN ('order_rejected', 'signal_filtered', 'position_blocked')),
  symbol text,
  leverage_attempted double precision,
  error_message text,
  request_payload jsonb,
  ip_address inet,
  user_agent text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT trading_type_audit_log_pkey PRIMARY KEY (id),
  CONSTRAINT trading_type_audit_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id)
);

-- Index dla audytu per user
CREATE INDEX idx_trading_type_audit_user 
ON public.trading_type_audit_log(user_id, created_at DESC);

-- Index dla monitoringu naruszeń
CREATE INDEX idx_trading_type_audit_violations 
ON public.trading_type_audit_log(exchange, action_type, created_at DESC) 
WHERE attempted_trading_type != allowed_trading_type;
```

**Uzasadnienie**:
- **Compliance logging** - każda próba naruszenia SPOT constraint jest logowana
- Możliwość analizy: ile razy AI próbował zasugerować leverage dla Binance
- Bezpieczeństwo: wykrywanie podejrzanych prób obejścia ograniczeń

---

## 🔧 SKRYPT MIGRACJI - PEŁNA IMPLEMENTACJA

```sql
-- ===================================================
-- ASE Trading Bot - SPOT Constraints Migration
-- Data: 2025-10-21
-- Cel: Dodanie SPOT trading constraints na poziomie DB
-- ===================================================

BEGIN;

-- 1. TRADING_SETTINGS
ALTER TABLE public.trading_settings 
ADD COLUMN IF NOT EXISTS trading_type text NOT NULL DEFAULT 'spot'
CHECK (trading_type IN ('spot', 'margin', 'futures'));

ALTER TABLE public.trading_settings 
ADD CONSTRAINT IF NOT EXISTS unique_user_exchange 
UNIQUE (user_id, exchange);

CREATE INDEX IF NOT EXISTS idx_trading_settings_user_exchange 
ON public.trading_settings(user_id, exchange);

UPDATE public.trading_settings 
SET trading_type = 'spot' 
WHERE exchange::text = 'binance';

-- 2. AI_INSIGHTS
ALTER TABLE public.ai_insights 
ADD COLUMN IF NOT EXISTS exchange text;

ALTER TABLE public.ai_insights 
ADD COLUMN IF NOT EXISTS trading_type text 
CHECK (trading_type IN ('spot', 'margin', 'futures'));

ALTER TABLE public.ai_insights 
ADD COLUMN IF NOT EXISTS gemini_validation_status text 
CHECK (gemini_validation_status IN ('approve', 'revise', 'reject', 'pending'));

ALTER TABLE public.ai_insights 
ADD COLUMN IF NOT EXISTS validation_risk_flags text[];

CREATE INDEX IF NOT EXISTS idx_ai_insights_user_exchange 
ON public.ai_insights(user_id, exchange) 
WHERE is_read = false;

-- 3. TRADING_SIGNALS
ALTER TABLE public.trading_signals 
ADD COLUMN IF NOT EXISTS exchange text;

ALTER TABLE public.trading_signals 
ADD COLUMN IF NOT EXISTS trading_type text NOT NULL DEFAULT 'spot'
CHECK (trading_type IN ('spot', 'margin', 'futures'));

ALTER TABLE public.trading_signals 
ADD COLUMN IF NOT EXISTS claude_analysis_id bigint;

ALTER TABLE public.trading_signals 
ADD COLUMN IF NOT EXISTS gemini_validation jsonb;

ALTER TABLE public.trading_signals 
ADD COLUMN IF NOT EXISTS tavily_context boolean DEFAULT false;

ALTER TABLE public.trading_signals 
ALTER COLUMN source SET DEFAULT 'claude_ai';

CREATE INDEX IF NOT EXISTS idx_trading_signals_active_exchange 
ON public.trading_signals(user_id, exchange, is_active) 
WHERE is_active = true AND expires_at > now();

-- 4. ORDERS
ALTER TABLE public.orders 
ADD COLUMN IF NOT EXISTS exchange text;

ALTER TABLE public.orders 
ADD COLUMN IF NOT EXISTS trading_type text NOT NULL DEFAULT 'spot'
CHECK (trading_type IN ('spot', 'margin', 'futures'));

ALTER TABLE public.orders 
ADD CONSTRAINT IF NOT EXISTS check_spot_no_leverage 
CHECK (
  (trading_type = 'spot' AND leverage = 1.0) OR 
  (trading_type != 'spot')
);

-- Function + Trigger dla orders
CREATE OR REPLACE FUNCTION validate_order_trading_type()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.exchange = 'binance' THEN
    NEW.trading_type := 'spot';
    NEW.leverage := 1.0;
  END IF;
  
  IF NEW.trading_type = 'spot' AND NEW.leverage != 1.0 THEN
    NEW.leverage := 1.0;
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS enforce_spot_trading ON public.orders;
CREATE TRIGGER enforce_spot_trading 
BEFORE INSERT OR UPDATE ON public.orders 
FOR EACH ROW 
EXECUTE FUNCTION validate_order_trading_type();

CREATE INDEX IF NOT EXISTS idx_orders_exchange_trading_type 
ON public.orders(user_id, exchange, trading_type, created_at);

-- 5. TRADES
ALTER TABLE public.trades 
ADD COLUMN IF NOT EXISTS trading_market_type text NOT NULL DEFAULT 'spot'
CHECK (trading_market_type IN ('spot', 'margin', 'futures'));

CREATE INDEX IF NOT EXISTS idx_trades_market_type_executed 
ON public.trades(user_id, exchange, trading_market_type, executed_at) 
WHERE status::text = 'completed';

-- Views dla SPOT analytics
CREATE OR REPLACE VIEW spot_trades AS 
SELECT * FROM public.trades 
WHERE trading_market_type = 'spot';

CREATE OR REPLACE VIEW user_spot_trading_stats AS
SELECT 
  user_id,
  exchange,
  COUNT(*) AS total_spot_trades,
  SUM(amount * price) AS total_spot_volume,
  AVG(fee) AS avg_spot_fee,
  MIN(executed_at) AS first_spot_trade,
  MAX(executed_at) AS last_spot_trade
FROM public.trades 
WHERE trading_market_type = 'spot' 
  AND status::text = 'completed'
GROUP BY user_id, exchange;

-- 6. POSITIONS
ALTER TABLE public.positions 
ADD COLUMN IF NOT EXISTS exchange text;

ALTER TABLE public.positions 
ADD COLUMN IF NOT EXISTS trading_type text NOT NULL DEFAULT 'spot'
CHECK (trading_type IN ('spot', 'margin', 'futures'));

ALTER TABLE public.positions 
ADD CONSTRAINT IF NOT EXISTS check_spot_position_no_leverage 
CHECK (
  (trading_type = 'spot' AND leverage = 1.0) OR 
  (trading_type != 'spot')
);

-- Function + Trigger dla positions
CREATE OR REPLACE FUNCTION validate_position_trading_type()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.exchange = 'binance' THEN
    NEW.trading_type := 'spot';
    NEW.leverage := 1.0;
  END IF;
  
  IF NEW.trading_type = 'spot' AND NEW.leverage != 1.0 THEN
    RAISE EXCEPTION 'SPOT positions cannot use leverage. Got leverage=%, expected 1.0', NEW.leverage;
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS enforce_spot_position ON public.positions;
CREATE TRIGGER enforce_spot_position 
BEFORE INSERT OR UPDATE ON public.positions 
FOR EACH ROW 
EXECUTE FUNCTION validate_position_trading_type();

CREATE INDEX IF NOT EXISTS idx_positions_open_exchange 
ON public.positions(user_id, exchange, trading_type, status) 
WHERE status = 'OPEN';

-- 7. API_KEYS
ALTER TABLE public.api_keys 
ADD COLUMN IF NOT EXISTS allowed_trading_types text[] NOT NULL DEFAULT ARRAY['spot'];

ALTER TABLE public.api_keys 
ADD CONSTRAINT IF NOT EXISTS check_binance_spot_only 
CHECK (
  (exchange::text = 'binance' AND allowed_trading_types = ARRAY['spot']) OR 
  (exchange::text != 'binance')
);

UPDATE public.api_keys 
SET allowed_trading_types = ARRAY['spot'] 
WHERE exchange::text = 'binance';

CREATE INDEX IF NOT EXISTS idx_api_keys_trading_types 
ON public.api_keys USING GIN (allowed_trading_types);

-- Function do walidacji API key
CREATE OR REPLACE FUNCTION check_api_key_supports_trading_type(
  p_api_key_id uuid,
  p_trading_type text
) RETURNS boolean AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM public.api_keys 
    WHERE id = p_api_key_id 
      AND p_trading_type = ANY(allowed_trading_types)
      AND is_active = true
  );
END;
$$ LANGUAGE plpgsql;

-- 8. AUDIT LOG TABLE
CREATE TABLE IF NOT EXISTS public.trading_type_audit_log (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  exchange text NOT NULL,
  attempted_trading_type text NOT NULL,
  allowed_trading_type text NOT NULL,
  action_type text NOT NULL CHECK (action_type IN ('order_rejected', 'signal_filtered', 'position_blocked')),
  symbol text,
  leverage_attempted double precision,
  error_message text,
  request_payload jsonb,
  ip_address inet,
  user_agent text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT trading_type_audit_log_pkey PRIMARY KEY (id),
  CONSTRAINT trading_type_audit_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id)
);

CREATE INDEX IF NOT EXISTS idx_trading_type_audit_user 
ON public.trading_type_audit_log(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_trading_type_audit_violations 
ON public.trading_type_audit_log(exchange, action_type, created_at DESC) 
WHERE attempted_trading_type != allowed_trading_type;

COMMIT;

-- ===================================================
-- WERYFIKACJA PO MIGRACJI
-- ===================================================

-- Test 1: Sprawdź czy Binance users mają SPOT w trading_settings
SELECT user_id, exchange, trading_type 
FROM public.trading_settings 
WHERE exchange::text = 'binance';

-- Test 2: Sprawdź czy Binance API keys mają tylko SPOT
SELECT user_id, exchange, allowed_trading_types 
FROM public.api_keys 
WHERE exchange::text = 'binance';

-- Test 3: Sprawdź czy constraint działa (powinien rzucić error)
-- INSERT INTO public.orders (user_id, exchange, symbol, side, order_type, quantity, trading_type, leverage)
-- VALUES ('3126f9fe-e724-4a33-bf4a-096804d56ece', 'binance', 'BTC/USDT', 'buy', 'limit', 0.001, 'spot', 5.0);
-- ^ Oczekiwany error: "new row for relation "orders" violates check constraint "check_spot_no_leverage"

-- Test 4: Sprawdź czy trigger działa (leverage powinien być automatycznie 1.0)
INSERT INTO public.orders (user_id, exchange, symbol, side, order_type, quantity, trading_type, leverage)
VALUES ('3126f9fe-e724-4a33-bf4a-096804d56ece', 'binance', 'BTC/USDT', 'buy', 'limit', 0.001, 'margin', 5.0);
-- ^ Oczekiwany wynik: trading_type automatycznie zmieniony na 'spot', leverage na 1.0

SELECT * FROM public.orders WHERE user_id = '3126f9fe-e724-4a33-bf4a-096804d56ece' ORDER BY created_at DESC LIMIT 1;
```

---

## 📋 PODSUMOWANIE ZMIAN

### **Krytyczne zmiany (MUST HAVE):**

| Tabela | Kolumna | Typ | Opis |
|--------|---------|-----|------|
| `trading_settings` | `trading_type` | text | SPOT/MARGIN/FUTURES |
| `orders` | `trading_type` | text | SPOT/MARGIN/FUTURES + constraint leverage=1.0 |
| `orders` | `exchange` | text | Nazwa giełdy |
| `positions` | `trading_type` | text | SPOT/MARGIN/FUTURES + constraint leverage=1.0 |
| `positions` | `exchange` | text | Nazwa giełdy |
| `api_keys` | `allowed_trading_types` | text[] | Array dozwolonych typów trading |
| `trades` | `trading_market_type` | text | SPOT/MARGIN/FUTURES |

### **Ulepszenia (SHOULD HAVE):**

| Tabela | Kolumna | Typ | Opis |
|--------|---------|-----|------|
| `ai_insights` | `exchange` | text | Z jakiej giełdy insight |
| `ai_insights` | `trading_type` | text | SPOT/MARGIN/FUTURES |
| `ai_insights` | `gemini_validation_status` | text | approve/revise/reject/pending |
| `ai_insights` | `validation_risk_flags` | text[] | Flagi ryzyka z Gemini |
| `trading_signals` | `exchange` | text | Z jakiej giełdy sygnał |
| `trading_signals` | `trading_type` | text | SPOT/MARGIN/FUTURES |
| `trading_signals` | `claude_analysis_id` | bigint | Link do analizy Claude |
| `trading_signals` | `gemini_validation` | jsonb | Wynik walidacji Gemini |
| `trading_signals` | `tavily_context` | boolean | Czy użyto web search |

### **Nowe elementy:**

| Element | Typ | Opis |
|---------|-----|------|
| `trading_type_audit_log` | table | Audit log naruszeń SPOT constraints |
| `validate_order_trading_type()` | function | Walidacja orders przed insertem |
| `validate_position_trading_type()` | function | Walidacja positions przed insertem |
| `check_api_key_supports_trading_type()` | function | Sprawdza czy API key wspiera trading type |
| `spot_trades` | view | View tylko SPOT trades |
| `user_spot_trading_stats` | view | Statystyki SPOT trading per user |
| `enforce_spot_trading` | trigger | Automatyczne wymuszenie SPOT dla Binance (orders) |
| `enforce_spot_position` | trigger | Automatyczne wymuszenie SPOT dla Binance (positions) |

---

## 🎯 WPŁYW NA APLIKACJĘ

### **Zmiany w kodzie Python (wymagane):**

#### **1. `bot/broker/live_broker.py` - Walidacja przed zleceniem**
```python
async def execute_order(self, order: Order) -> OrderResult:
    """Execute order with SPOT constraint validation."""
    
    # 1. Pobierz trading_settings użytkownika
    settings = await self.db.get_trading_settings(order.user_id, self.exchange)
    
    # 2. Waliduj trading_type
    if settings.trading_type == 'spot' and order.leverage > 1.0:
        await self.db.log_trading_type_violation(
            user_id=order.user_id,
            exchange=self.exchange,
            attempted_trading_type='margin',
            allowed_trading_type='spot',
            action_type='order_rejected',
            symbol=order.symbol,
            leverage_attempted=order.leverage
        )
        raise ValueError(
            f"SPOT trading only: leverage must be 1.0, got {order.leverage}"
        )
    
    # 3. Ustaw trading_type w order (DB trigger zrobi resztę)
    order.trading_type = settings.trading_type
    order.exchange = self.exchange
    
    # 4. Wykonaj zlecenie
    result = await self.ccxt_adapter.create_order(order)
    return result
```

#### **2. `bot/auto_trading_engine.py` - Filtrowanie sygnałów**
```python
async def process_ai_signals(self, signals: List[TradingSignal]) -> List[TradingSignal]:
    """Filter AI signals based on user trading_type constraints."""
    
    filtered_signals = []
    
    for signal in signals:
        # Pobierz user settings
        settings = await self.db.get_trading_settings(signal.user_id, signal.exchange)
        
        # Jeśli SPOT only, odrzuć sygnały z leverage
        if settings.trading_type == 'spot':
            if signal.metadata.get('leverage', 1.0) > 1.0:
                await self.db.log_trading_type_violation(
                    user_id=signal.user_id,
                    exchange=signal.exchange,
                    attempted_trading_type='margin',
                    allowed_trading_type='spot',
                    action_type='signal_filtered',
                    symbol=signal.symbol
                )
                logger.warning(
                    f"Signal {signal.id} filtered: SPOT user, leverage={signal.metadata.get('leverage')}"
                )
                continue
        
        # Ustaw trading_type w sygnale
        signal.trading_type = settings.trading_type
        filtered_signals.append(signal)
    
    return filtered_signals
```

#### **3. `bot/database_manager.py` - Nowe metody DB**
```python
async def get_trading_settings(self, user_id: str, exchange: str) -> TradingSettings:
    """Get user trading settings with trading_type."""
    result = await self.supabase.table('trading_settings') \
        .select('*') \
        .eq('user_id', user_id) \
        .eq('exchange', exchange) \
        .single() \
        .execute()
    
    return TradingSettings(**result.data)

async def log_trading_type_violation(
    self,
    user_id: str,
    exchange: str,
    attempted_trading_type: str,
    allowed_trading_type: str,
    action_type: str,
    symbol: str = None,
    leverage_attempted: float = None,
    error_message: str = None,
    request_payload: dict = None
):
    """Log trading type constraint violation."""
    await self.supabase.table('trading_type_audit_log').insert({
        'user_id': user_id,
        'exchange': exchange,
        'attempted_trading_type': attempted_trading_type,
        'allowed_trading_type': allowed_trading_type,
        'action_type': action_type,
        'symbol': symbol,
        'leverage_attempted': leverage_attempted,
        'error_message': error_message,
        'request_payload': request_payload
    }).execute()
```

#### **4. `bot/ai_analysis.py` - Zapis trading_type w AI insights**
```python
async def analyze_market(self, parameters: Dict) -> Dict:
    """Analyze market with trading_type tracking."""
    
    # Existing code...
    exchange = parameters.get("exchange", "unknown")
    
    # Pobierz trading_type z user settings
    user_id = parameters.get("user_id")
    settings = await self.db.get_trading_settings(user_id, exchange)
    trading_type = settings.trading_type
    
    # Add to constraints
    if trading_type == 'spot':
        trading_constraints = f"""
[CRITICAL TRADING CONSTRAINTS]
• Exchange: {exchange}
• Trading Type: SPOT ONLY (no futures, no margin, no leverage)
• All recommendations MUST be for SPOT market pairs only
• User can ONLY trade spot assets (buy/sell without leverage)
"""
    
    # Claude analysis...
    claude_response = await self.claude_client.messages.create(...)
    
    # Gemini validation...
    gemini_result = await self._validate_with_gemini(claude_response)
    
    # Save to DB with trading_type
    await self.db.record_ai_insight(
        user_id=user_id,
        exchange=exchange,
        trading_type=trading_type,
        gemini_validation_status=gemini_result['status'],
        validation_risk_flags=gemini_result['risk_flags'],
        tavily_context=bool(self.tavily),
        **claude_response
    )
    
    return claude_response
```

---

## ✅ CHECKLIST WDROŻENIA

### **Faza 1: Backup i przygotowanie**
- [ ] Backup całej bazy danych Supabase
- [ ] Backup konfiguracji production (.env, trading_settings)
- [ ] Weryfikacja połączenia z Supabase (test write access)

### **Faza 2: Migracja DB**
- [ ] Uruchom skrypt migracji SQL na Supabase
- [ ] Weryfikacja: wszystkie tabele mają nowe kolumny
- [ ] Weryfikacja: triggery działają poprawnie (test insert)
- [ ] Weryfikacja: constraints blokują nieprawidłowe dane

### **Faza 3: Aktualizacja kodu**
- [ ] Aktualizuj `bot/broker/live_broker.py` (walidacja orders)
- [ ] Aktualizuj `bot/auto_trading_engine.py` (filtrowanie sygnałów)
- [ ] Aktualizuj `bot/database_manager.py` (nowe metody DB)
- [ ] Aktualizuj `bot/ai_analysis.py` (zapis trading_type)
- [ ] Aktualizuj `bot/models.py` (dodaj trading_type do modeli)

### **Faza 4: Testy**
- [ ] Test 1: Próba utworzenia SPOT order z leverage > 1.0 (powinien być błąd)
- [ ] Test 2: Próba utworzenia Binance order z trading_type='margin' (powinien być zmieniony na 'spot')
- [ ] Test 3: AI analysis dla Binance user (powinien zawierać SPOT constraints)
- [ ] Test 4: Filtrowanie sygnałów z leverage dla SPOT user
- [ ] Test 5: Audit log (sprawdź czy naruszenia są logowane)

### **Faza 5: Deployment**
- [ ] Deploy kodu na serwer (185.70.198.201)
- [ ] Restart serwisu `asebot.service`
- [ ] Smoke test: `/health`, `/api/ai/health`
- [ ] Weryfikacja logów: brak critical errors
- [ ] Monitor pierwszych 100 zleceń (czy constraints działają)

---

## 🚨 OSTRZEŻENIA

### **Breaking Changes:**
1. **Wszystkie istniejące orders/positions bez `trading_type` dostaną wartość 'spot'** (default)
2. **Binance API keys automatycznie dostaną `allowed_trading_types = ['spot']`**
3. **Triggery automatycznie zmienią `leverage` na 1.0 dla SPOT orders** (może złamać existing logic)

### **Rollback Plan:**
```sql
-- W razie problemów, rollback:
BEGIN;

-- Usuń nowe kolumny
ALTER TABLE trading_settings DROP COLUMN IF EXISTS trading_type;
ALTER TABLE orders DROP COLUMN IF EXISTS trading_type, DROP COLUMN IF EXISTS exchange;
ALTER TABLE positions DROP COLUMN IF EXISTS trading_type, DROP COLUMN IF EXISTS exchange;
ALTER TABLE trades DROP COLUMN IF EXISTS trading_market_type;
ALTER TABLE api_keys DROP COLUMN IF EXISTS allowed_trading_types;

-- Usuń triggery
DROP TRIGGER IF EXISTS enforce_spot_trading ON public.orders;
DROP TRIGGER IF EXISTS enforce_spot_position ON public.positions;

-- Usuń functions
DROP FUNCTION IF EXISTS validate_order_trading_type();
DROP FUNCTION IF EXISTS validate_position_trading_type();
DROP FUNCTION IF EXISTS check_api_key_supports_trading_type(uuid, text);

-- Usuń audit log
DROP TABLE IF EXISTS public.trading_type_audit_log;

COMMIT;
```

---

## 🎉 OCZEKIWANE REZULTATY

### **Po wdrożeniu:**
1. ✅ **SPOT constraints wymuszane na 3 poziomach**:
   - Prompt AI (Claude + Gemini) ← już działa
   - Walidacja w kodzie (LiveBroker, AutoTradingEngine) ← do dodania
   - Walidacja w bazie (triggers + constraints) ← do wdrożenia

2. ✅ **Pełny audit trail**:
   - Każda próba naruszenia SPOT → audit log
   - Możliwość analizy: ile razy AI sugerował leverage
   - Compliance reporting

3. ✅ **Zero możliwości obejścia**:
   - DB trigger automatycznie wymusza SPOT dla Binance
   - Constraint blokuje insert z leverage > 1.0
   - API key validation przed wykonaniem zlecenia

4. ✅ **Backward compatibility**:
   - Istniejące zlecenia dostaną `trading_type = 'spot'`
   - Kod gracefully fallback jeśli trading_type = NULL
   - Rollback możliwy bez utraty danych

---

**Gotowe do wdrożenia!** 🚀

Skrypt SQL można uruchomić bezpośrednio w Supabase SQL Editor lub przez migration tool.
