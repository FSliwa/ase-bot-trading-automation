-- ============================================================================
-- DCA Tables Verification Script
-- Run this AFTER the migration to verify everything was created correctly
-- ============================================================================

-- 1. Check if tables exist
SELECT 
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'public' 
AND table_name IN ('dca_positions', 'dca_orders', 'dca_settings')
ORDER BY table_name;

-- Expected output:
-- | table_name     | column_count |
-- |----------------|--------------|
-- | dca_orders     | 17           |
-- | dca_positions  | 27           |
-- | dca_settings   | 13           |

-- 2. Check indexes
SELECT 
    indexname,
    tablename
FROM pg_indexes
WHERE tablename LIKE 'dca%'
ORDER BY tablename, indexname;

-- 3. Check RLS is enabled
SELECT 
    tablename,
    rowsecurity
FROM pg_tables
WHERE tablename LIKE 'dca%';

-- Expected: all should have rowsecurity = true

-- 4. Check RLS policies
SELECT 
    tablename,
    policyname,
    cmd
FROM pg_policies
WHERE tablename LIKE 'dca%'
ORDER BY tablename, policyname;

-- 5. Test insert (will fail if RLS blocks - use service role)
-- INSERT INTO dca_settings (user_id, dca_enabled) VALUES ('your-user-id', true);

-- 6. Cleanup test data
-- DELETE FROM dca_settings WHERE user_id = 'your-user-id';
