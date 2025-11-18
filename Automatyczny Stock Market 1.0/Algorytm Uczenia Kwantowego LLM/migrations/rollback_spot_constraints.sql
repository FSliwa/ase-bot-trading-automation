-- ===================================================
-- ASE Trading Bot - SPOT Constraints ROLLBACK
-- Data: 2025-10-21
-- Cel: Wycofanie zmian w przypadku problemów
-- UWAGA: Użyj TYLKO jeśli migracja spowodowała problemy!
-- ===================================================

BEGIN;

-- ===================================================
-- ROLLBACK - Usuwanie w odwrotnej kolejności
-- ===================================================

-- 8. Usuń audit log table
DROP TABLE IF EXISTS public.trading_type_audit_log CASCADE;

-- 7. Usuń zmiany w api_keys
ALTER TABLE public.api_keys 
DROP CONSTRAINT IF EXISTS check_binance_spot_only;

DROP INDEX IF EXISTS idx_api_keys_trading_types;

ALTER TABLE public.api_keys 
DROP COLUMN IF EXISTS allowed_trading_types;

DROP FUNCTION IF EXISTS check_api_key_supports_trading_type(uuid, text);

-- 6. Usuń zmiany w positions
DROP TRIGGER IF EXISTS enforce_spot_position ON public.positions;
DROP FUNCTION IF EXISTS validate_position_trading_type();

ALTER TABLE public.positions 
DROP CONSTRAINT IF EXISTS check_spot_position_no_leverage;

DROP INDEX IF EXISTS idx_positions_open_exchange;

ALTER TABLE public.positions 
DROP COLUMN IF EXISTS trading_type;

ALTER TABLE public.positions 
DROP COLUMN IF EXISTS exchange;

-- 5. Usuń zmiany w trades
DROP VIEW IF EXISTS user_spot_trading_stats;
DROP VIEW IF EXISTS spot_trades;

DROP INDEX IF EXISTS idx_trades_market_type_executed;

ALTER TABLE public.trades 
DROP COLUMN IF EXISTS trading_market_type;

-- 4. Usuń zmiany w orders
DROP TRIGGER IF EXISTS enforce_spot_trading ON public.orders;
DROP FUNCTION IF EXISTS validate_order_trading_type();

ALTER TABLE public.orders 
DROP CONSTRAINT IF EXISTS check_spot_no_leverage;

DROP INDEX IF EXISTS idx_orders_exchange_trading_type;

ALTER TABLE public.orders 
DROP COLUMN IF EXISTS trading_type;

ALTER TABLE public.orders 
DROP COLUMN IF EXISTS exchange;

-- 3. Usuń zmiany w trading_signals
DROP INDEX IF EXISTS idx_trading_signals_trading_type;
DROP INDEX IF EXISTS idx_trading_signals_active_exchange;

ALTER TABLE public.trading_signals 
ALTER COLUMN source SET DEFAULT 'gemini_ai';

ALTER TABLE public.trading_signals 
DROP COLUMN IF EXISTS tavily_context;

ALTER TABLE public.trading_signals 
DROP COLUMN IF EXISTS gemini_validation;

ALTER TABLE public.trading_signals 
DROP COLUMN IF EXISTS claude_analysis_id;

ALTER TABLE public.trading_signals 
DROP COLUMN IF EXISTS trading_type;

ALTER TABLE public.trading_signals 
DROP COLUMN IF EXISTS exchange;

-- 2. Usuń zmiany w ai_insights
DROP INDEX IF EXISTS idx_ai_insights_active_priority;
DROP INDEX IF EXISTS idx_ai_insights_user_exchange;

ALTER TABLE public.ai_insights 
DROP COLUMN IF EXISTS validation_risk_flags;

ALTER TABLE public.ai_insights 
DROP COLUMN IF EXISTS gemini_validation_status;

ALTER TABLE public.ai_insights 
DROP COLUMN IF EXISTS trading_type;

ALTER TABLE public.ai_insights 
DROP COLUMN IF EXISTS exchange;

-- 1. Usuń zmiany w trading_settings
DROP INDEX IF EXISTS idx_trading_settings_user_exchange;

ALTER TABLE public.trading_settings 
DROP CONSTRAINT IF EXISTS unique_user_exchange;

ALTER TABLE public.trading_settings 
DROP COLUMN IF EXISTS trading_type;

COMMIT;

-- ===================================================
-- WERYFIKACJA PO ROLLBACK
-- ===================================================

-- Test 1: Sprawdź czy kolumny zostały usunięte
SELECT 
  'Test 1: Kolumny usunięte' as test_name,
  COUNT(*) as should_be_zero
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

-- Test 2: Sprawdź czy triggery zostały usunięte
SELECT 
  'Test 2: Triggery usunięte' as test_name,
  COUNT(*) as should_be_zero
FROM information_schema.triggers 
WHERE trigger_schema = 'public' 
  AND trigger_name IN ('enforce_spot_trading', 'enforce_spot_position');

-- Test 3: Sprawdź czy audit log został usunięty
SELECT 
  'Test 3: Audit log usunięty' as test_name,
  COUNT(*) as should_be_zero
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name = 'trading_type_audit_log';

-- Test 4: Sprawdź czy views zostały usunięte
SELECT 
  'Test 4: Views usunięte' as test_name,
  COUNT(*) as should_be_zero
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
  ⏮️  SPOT Constraints Rollback - ZAKOŃCZONY
  ===================================================
  
  Wycofane zmiany:
  ✅ Wszystkie nowe kolumny usunięte
  ✅ Wszystkie triggery usunięte
  ✅ Wszystkie constraints usunięte
  ✅ Wszystkie functions usunięte
  ✅ Wszystkie indexes usunięte
  ✅ Wszystkie views usunięte
  ✅ Audit log table usunięta
  
  Baza danych przywrócona do stanu sprzed migracji.
  
  Następne kroki:
  1. Sprawdź wyniki testów weryfikacyjnych powyżej
  2. Restart serwisu: sudo systemctl restart asebot.service
  3. Jeśli potrzebujesz ponownie migracji, napraw błędy i uruchom ponownie
  
  ===================================================
  ';
END $$;
