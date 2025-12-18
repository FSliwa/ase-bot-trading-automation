-- =============================================================================
-- MIGRATION: Create monitored_positions table for Hybrid Persistence
-- Version: 4.1.1
-- Date: 2025-12-14
-- Description: Stores Position Monitor state for crash recovery
-- =============================================================================

-- NOTE: Run this migration in Supabase SQL Editor
-- If you get errors about missing columns, run in TWO STEPS:
-- 1. First run everything up to "STEP 2" comment
-- 2. Then run the rest

-- ======================= STEP 1: CREATE TABLE ===============================

-- Tabela przechowuje pozycje monitorowane przez PositionMonitorService
-- RAM = Primary source of truth (szybkość)
-- Supabase = Persystencja + Backup (co 5-10 sekund batch sync)
-- On startup = Load from Supabase → RAM

DROP TABLE IF EXISTS monitored_positions CASCADE;

CREATE TABLE monitored_positions (
    -- Primary key (unique per user+symbol)
    position_key TEXT PRIMARY KEY,  -- Format: "user_id:symbol" or "symbol"
    
    -- User identification (UUID stored as text for flexibility)
    user_id TEXT,  -- Can reference auth.users(id) but stored as TEXT for flexibility
    
    -- Position basics
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('long', 'short')),
    entry_price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    
    -- SL/TP levels
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    original_stop_loss DECIMAL(20, 8),
    
    -- Leverage (K1 FIX)
    leverage DECIMAL(10, 2) DEFAULT 1.0,
    leverage_aware_sl_tp BOOLEAN DEFAULT TRUE,
    
    -- Trailing Stop
    trailing_enabled BOOLEAN DEFAULT FALSE,
    trailing_distance_pct DECIMAL(10, 4) DEFAULT 2.0,
    highest_price DECIMAL(20, 8),
    lowest_price DECIMAL(20, 8),
    trailing_activated BOOLEAN DEFAULT FALSE,
    
    -- Dynamic SL/TP
    dynamic_sl_enabled BOOLEAN DEFAULT FALSE,
    
    -- Time-based exit
    max_hold_hours DECIMAL(10, 2) DEFAULT 12.0,
    
    -- Partial TP tracking
    partial_tp_executed JSONB DEFAULT '[]',
    original_quantity DECIMAL(20, 8),
    
    -- Liquidation monitoring (v4.0)
    liquidation_price DECIMAL(20, 8),
    liquidation_risk_level TEXT DEFAULT 'safe' CHECK (
        liquidation_risk_level IN ('safe', 'warning', 'danger', 'critical', 'liquidated')
    ),
    liquidation_warnings_sent INTEGER DEFAULT 0,
    auto_close_attempted BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    last_sync TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    
    -- Soft delete flag (allows history tracking)
    is_active BOOLEAN DEFAULT TRUE
);

-- ======================= STEP 2: INDEXES ====================================
-- INDEXES for performance
-- =============================================================================

-- Index for user queries
CREATE INDEX IF NOT EXISTS idx_monitored_positions_user_id 
ON monitored_positions(user_id);

-- Index for active positions (partial index - most common query)
CREATE INDEX IF NOT EXISTS idx_monitored_positions_active 
ON monitored_positions(position_key) WHERE (is_active = TRUE);

-- Index for symbol lookups
CREATE INDEX IF NOT EXISTS idx_monitored_positions_symbol 
ON monitored_positions(symbol);

-- Composite index for user+active queries (partial index)
CREATE INDEX IF NOT EXISTS idx_monitored_positions_user_active 
ON monitored_positions(user_id) WHERE (is_active = TRUE);

-- =============================================================================
-- ROW LEVEL SECURITY (RLS)
-- =============================================================================

-- Enable RLS
ALTER TABLE monitored_positions ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own positions
CREATE POLICY "Users can view own monitored positions"
ON monitored_positions FOR SELECT
USING (auth.uid()::text = user_id OR auth.uid() IS NULL);

-- Policy: Service role can do everything (for backend sync)
CREATE POLICY "Service role full access"
ON monitored_positions FOR ALL
USING (auth.role() = 'service_role');

-- =============================================================================
-- CLEANUP FUNCTION (optional - remove old closed positions after 30 days)
-- =============================================================================

CREATE OR REPLACE FUNCTION cleanup_old_monitored_positions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM monitored_positions
    WHERE is_active = FALSE 
    AND closed_at < NOW() - INTERVAL '30 days';
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE monitored_positions IS 'Stores Position Monitor RAM state for hybrid persistence (v4.1)';
COMMENT ON COLUMN monitored_positions.position_key IS 'Unique key: user_id:symbol or just symbol';
COMMENT ON COLUMN monitored_positions.leverage_aware_sl_tp IS 'K1 FIX: If true, SL/TP % applies to capital, not price';
COMMENT ON COLUMN monitored_positions.partial_tp_executed IS 'JSON array of executed partial TP levels [0,1,2]';
COMMENT ON COLUMN monitored_positions.is_active IS 'Soft delete flag - false means position was closed';
COMMENT ON COLUMN monitored_positions.last_sync IS 'Last sync timestamp from RAM to Supabase';

-- =============================================================================
-- SAMPLE QUERIES FOR DEBUGGING
-- =============================================================================

-- Get all active positions
-- SELECT * FROM monitored_positions WHERE is_active = TRUE;

-- Get positions at liquidation risk
-- SELECT * FROM monitored_positions 
-- WHERE is_active = TRUE 
-- AND liquidation_risk_level IN ('danger', 'critical');

-- Get user's positions
-- SELECT * FROM monitored_positions 
-- WHERE user_id = 'UUID_HERE' AND is_active = TRUE;

-- Cleanup old data
-- SELECT cleanup_old_monitored_positions();
