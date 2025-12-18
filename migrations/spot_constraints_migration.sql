-- ===================================================
-- ASE Trading Bot - SPOT Constraints Migration
-- Data: 2025-10-21
-- Cel: Dodanie SPOT trading constraints na poziomie DB
-- Autor: ASE Bot Development Team
-- ===================================================
-- INSTRUKCJA:
-- 1. Zrób backup bazy danych przed uruchomieniem
-- 2. Uruchom w Supabase SQL Editor
-- 3. Sprawdź testy weryfikacyjne na końcu
-- ===================================================

BEGIN;

-- ===================================================
-- 1. TRADING_SETTINGS - Dodanie trading_type
-- ===================================================

-- Dodaj kolumnę trading_type
ALTER TABLE public.trading_settings 
ADD COLUMN IF NOT EXISTS trading_type text NOT NULL DEFAULT 'spot'
CHECK (trading_type IN ('spot', 'margin', 'futures'));

-- Unique constraint: jeden user = jedno ustawienie na giełdę
ALTER TABLE public.trading_settings 
ADD CONSTRAINT IF NOT EXISTS unique_user_exchange 
UNIQUE (user_id, exchange);

-- Index dla szybszego wyszukiwania
CREATE INDEX IF NOT EXISTS idx_trading_settings_user_exchange 
ON public.trading_settings(user_id, exchange);

-- Update dla wszystkich Binance users (wymuszenie SPOT)
UPDATE public.trading_settings 
SET trading_type = 'spot' 
WHERE exchange::text = 'binance';

-- ===================================================
-- 2. AI_INSIGHTS - Rozbudowa o exchange i validation
-- ===================================================

-- Dodaj exchange
ALTER TABLE public.ai_insights 
ADD COLUMN IF NOT EXISTS exchange text;

-- Dodaj trading_type
ALTER TABLE public.ai_insights 
ADD COLUMN IF NOT EXISTS trading_type text 
CHECK (trading_type IN ('spot', 'margin', 'futures'));

-- Dodaj gemini_validation_status
ALTER TABLE public.ai_insights 
ADD COLUMN IF NOT EXISTS gemini_validation_status text 
CHECK (gemini_validation_status IN ('approve', 'revise', 'reject', 'pending'));

-- Dodaj validation_risk_flags
ALTER TABLE public.ai_insights 
ADD COLUMN IF NOT EXISTS validation_risk_flags text[];

-- Index dla filtrowania insights per exchange
CREATE INDEX IF NOT EXISTS idx_ai_insights_user_exchange 
ON public.ai_insights(user_id, exchange) 
WHERE is_read = false;

-- Index dla aktywnych insights
CREATE INDEX IF NOT EXISTS idx_ai_insights_active_priority 
ON public.ai_insights(priority, created_at) 
WHERE is_read = false AND expires_at > now();

-- ===================================================
-- 3. TRADING_SIGNALS - Rozbudowa o AI tracking
-- ===================================================

-- Dodaj exchange
ALTER TABLE public.trading_signals 
ADD COLUMN IF NOT EXISTS exchange text;

-- Dodaj trading_type
ALTER TABLE public.trading_signals 
ADD COLUMN IF NOT EXISTS trading_type text NOT NULL DEFAULT 'spot'
CHECK (trading_type IN ('spot', 'margin', 'futures'));

-- Dodaj claude_analysis_id (link do ai_analyses)
ALTER TABLE public.trading_signals 
ADD COLUMN IF NOT EXISTS claude_analysis_id bigint 
REFERENCES public.ai_analyses(id);

-- Dodaj gemini_validation (JSON z wynikiem walidacji)
ALTER TABLE public.trading_signals 
ADD COLUMN IF NOT EXISTS gemini_validation jsonb;

-- Dodaj tavily_context (czy użyto web search)
ALTER TABLE public.trading_signals 
ADD COLUMN IF NOT EXISTS tavily_context boolean DEFAULT false;

-- Update source (domyślnie 'claude_ai')
ALTER TABLE public.trading_signals 
ALTER COLUMN source SET DEFAULT 'claude_ai';

-- Index dla aktywnych sygnałów per exchange
CREATE INDEX IF NOT EXISTS idx_trading_signals_active_exchange 
ON public.trading_signals(user_id, exchange, is_active) 
WHERE is_active = true AND (expires_at IS NULL OR expires_at > now());

-- Index dla sygnałów per trading_type
CREATE INDEX IF NOT EXISTS idx_trading_signals_trading_type 
ON public.trading_signals(trading_type, created_at) 
WHERE is_active = true;

-- ===================================================
-- 4. ORDERS - Dodanie trading_type i walidacji
-- ===================================================

-- Dodaj exchange
ALTER TABLE public.orders 
ADD COLUMN IF NOT EXISTS exchange text;

-- Dodaj trading_type
ALTER TABLE public.orders 
ADD COLUMN IF NOT EXISTS trading_type text NOT NULL DEFAULT 'spot'
CHECK (trading_type IN ('spot', 'margin', 'futures'));

-- Constraint: SPOT orders MUSZĄ mieć leverage = 1.0
ALTER TABLE public.orders 
ADD CONSTRAINT IF NOT EXISTS check_spot_no_leverage 
CHECK (
  (trading_type = 'spot' AND leverage = 1.0) OR 
  (trading_type != 'spot')
);

-- Function do walidacji przed insertem
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

-- Trigger do automatycznej walidacji
DROP TRIGGER IF EXISTS enforce_spot_trading ON public.orders;
CREATE TRIGGER enforce_spot_trading 
BEFORE INSERT OR UPDATE ON public.orders 
FOR EACH ROW 
EXECUTE FUNCTION validate_order_trading_type();

-- Index dla zleceń per exchange + trading_type
CREATE INDEX IF NOT EXISTS idx_orders_exchange_trading_type 
ON public.orders(user_id, exchange, trading_type, created_at);

-- ===================================================
-- 5. TRADES - Dodanie trading_market_type
-- ===================================================

-- Dodaj trading_market_type (nazwa inna niż trade_type żeby uniknąć kolizji)
ALTER TABLE public.trades 
ADD COLUMN IF NOT EXISTS trading_market_type text NOT NULL DEFAULT 'spot'
CHECK (trading_market_type IN ('spot', 'margin', 'futures'));

-- Index dla analityki trades per market type
CREATE INDEX IF NOT EXISTS idx_trades_market_type_executed 
ON public.trades(user_id, exchange, trading_market_type, executed_at) 
WHERE status::text = 'completed';

-- View dla SPOT-only trades
CREATE OR REPLACE VIEW spot_trades AS 
SELECT * FROM public.trades 
WHERE trading_market_type = 'spot';

-- View dla statystyk SPOT trading per user
CREATE OR REPLACE VIEW user_spot_trading_stats AS
SELECT 
  user_id,
  exchange::text as exchange,
  COUNT(*) AS total_spot_trades,
  SUM(amount * price) AS total_spot_volume,
  AVG(fee) AS avg_spot_fee,
  MIN(executed_at) AS first_spot_trade,
  MAX(executed_at) AS last_spot_trade
FROM public.trades 
WHERE trading_market_type = 'spot' 
  AND status::text = 'completed'
GROUP BY user_id, exchange::text;

-- ===================================================
-- 6. POSITIONS - Dodanie trading_type i walidacji
-- ===================================================

-- Dodaj exchange
ALTER TABLE public.positions 
ADD COLUMN IF NOT EXISTS exchange text;

-- Dodaj trading_type
ALTER TABLE public.positions 
ADD COLUMN IF NOT EXISTS trading_type text NOT NULL DEFAULT 'spot'
CHECK (trading_type IN ('spot', 'margin', 'futures'));

-- Constraint: SPOT positions MUSZĄ mieć leverage = 1.0
ALTER TABLE public.positions 
ADD CONSTRAINT IF NOT EXISTS check_spot_position_no_leverage 
CHECK (
  (trading_type = 'spot' AND leverage = 1.0) OR 
  (trading_type != 'spot')
);

-- Function do walidacji przed otwarciem pozycji
CREATE OR REPLACE FUNCTION validate_position_trading_type()
RETURNS TRIGGER AS $$
BEGIN
  -- Jeśli exchange = 'binance', wymuś trading_type = 'spot'
  IF NEW.exchange = 'binance' THEN
    NEW.trading_type := 'spot';
    NEW.leverage := 1.0;
  END IF;
  
  -- Jeśli trading_type = 'spot', wymuś leverage = 1.0 (z błędem)
  IF NEW.trading_type = 'spot' AND NEW.leverage != 1.0 THEN
    RAISE EXCEPTION 'SPOT positions cannot use leverage. Got leverage=%, expected 1.0', NEW.leverage;
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger do automatycznej walidacji
DROP TRIGGER IF EXISTS enforce_spot_position ON public.positions;
CREATE TRIGGER enforce_spot_position 
BEFORE INSERT OR UPDATE ON public.positions 
FOR EACH ROW 
EXECUTE FUNCTION validate_position_trading_type();

-- Index dla otwartych pozycji per exchange + trading_type
CREATE INDEX IF NOT EXISTS idx_positions_open_exchange 
ON public.positions(user_id, exchange, trading_type, status) 
WHERE status = 'OPEN';

-- ===================================================
-- 7. API_KEYS - Dodanie allowed_trading_types
-- ===================================================

-- Dodaj allowed_trading_types (array)
ALTER TABLE public.api_keys 
ADD COLUMN IF NOT EXISTS allowed_trading_types text[] NOT NULL DEFAULT ARRAY['spot'];

-- Constraint: Binance API keys MOGĄ TYLKO SPOT
ALTER TABLE public.api_keys 
ADD CONSTRAINT IF NOT EXISTS check_binance_spot_only 
CHECK (
  (exchange::text = 'binance' AND allowed_trading_types = ARRAY['spot']) OR 
  (exchange::text != 'binance')
);

-- Update istniejących Binance keys
UPDATE public.api_keys 
SET allowed_trading_types = ARRAY['spot'] 
WHERE exchange::text = 'binance';

-- Index dla szybkiego wyszukiwania keys per trading type
CREATE INDEX IF NOT EXISTS idx_api_keys_trading_types 
ON public.api_keys USING GIN (allowed_trading_types);

-- Function do walidacji zgodności API key z trading type
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

-- ===================================================
-- 8. TRADING_TYPE_AUDIT_LOG - Nowa tabela
-- ===================================================

-- Tabela do trackingu prób naruszenia SPOT constraints
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

-- Index dla audytu per user
CREATE INDEX IF NOT EXISTS idx_trading_type_audit_user 
ON public.trading_type_audit_log(user_id, created_at DESC);

-- Index dla monitoringu naruszeń
CREATE INDEX IF NOT EXISTS idx_trading_type_audit_violations 
ON public.trading_type_audit_log(exchange, action_type, created_at DESC) 
WHERE attempted_trading_type != allowed_trading_type;

COMMIT;

-- ===================================================
-- WERYFIKACJA PO MIGRACJI
-- ===================================================

-- Test 1: Sprawdź czy Binance users mają SPOT w trading_settings
SELECT 
  'Test 1: Binance users trading_type' as test_name,
  COUNT(*) as binance_users,
  COUNT(CASE WHEN trading_type = 'spot' THEN 1 END) as spot_users
FROM public.trading_settings 
WHERE exchange::text = 'binance';

-- Test 2: Sprawdź czy Binance API keys mają tylko SPOT
SELECT 
  'Test 2: Binance API keys' as test_name,
  COUNT(*) as total_keys,
  COUNT(CASE WHEN allowed_trading_types = ARRAY['spot'] THEN 1 END) as spot_only_keys
FROM public.api_keys 
WHERE exchange::text = 'binance';

-- Test 3: Sprawdź czy nowe kolumny istnieją
SELECT 
  'Test 3: Schema verification' as test_name,
  COUNT(DISTINCT column_name) as new_columns_count
FROM information_schema.columns 
WHERE table_schema = 'public' 
  AND column_name IN (
    'trading_type', 
    'trading_market_type', 
    'allowed_trading_types',
    'gemini_validation_status',
    'claude_analysis_id',
    'tavily_context'
  );

-- Test 4: Sprawdź czy triggery istnieją
SELECT 
  'Test 4: Triggers verification' as test_name,
  COUNT(*) as triggers_count
FROM information_schema.triggers 
WHERE trigger_schema = 'public' 
  AND trigger_name IN ('enforce_spot_trading', 'enforce_spot_position');

-- Test 5: Sprawdź czy audit log table istnieje
SELECT 
  'Test 5: Audit log table' as test_name,
  COUNT(*) as table_exists
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name = 'trading_type_audit_log';

-- Test 6: Sprawdź czy views istnieją
SELECT 
  'Test 6: Views verification' as test_name,
  COUNT(*) as views_count
FROM information_schema.views 
WHERE table_schema = 'public' 
  AND table_name IN ('spot_trades', 'user_spot_trading_stats');

-- ===================================================
-- KOŃCOWA WIADOMOŚĆ
-- ===================================================

DO $$
BEGIN
  RAISE NOTICE '
  ===================================================
  ✅ SPOT Constraints Migration - ZAKOŃCZONA
  ===================================================
  
  Wykonane zmiany:
  ✅ 1. trading_settings - dodano trading_type
  ✅ 2. ai_insights - dodano exchange, trading_type, validation
  ✅ 3. trading_signals - dodano exchange, trading_type, AI tracking
  ✅ 4. orders - dodano trading_type, exchange + trigger
  ✅ 5. trades - dodano trading_market_type + views
  ✅ 6. positions - dodano trading_type, exchange + trigger
  ✅ 7. api_keys - dodano allowed_trading_types + constraint
  ✅ 8. trading_type_audit_log - nowa tabela
  
  Triggery aktywne:
  ✅ enforce_spot_trading (orders)
  ✅ enforce_spot_position (positions)
  
  Constraints aktywne:
  ✅ check_spot_no_leverage (orders)
  ✅ check_spot_position_no_leverage (positions)
  ✅ check_binance_spot_only (api_keys)
  
  Następne kroki:
  1. Sprawdź wyniki testów weryfikacyjnych powyżej
  2. Zaktualizuj kod Python (LiveBroker, AutoTradingEngine)
  3. Restart serwisu: sudo systemctl restart asebot.service
  4. Monitor logów: journalctl -u asebot.service -f
  
  ===================================================
  ';
END $$;
