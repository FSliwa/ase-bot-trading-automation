-- ============================================================================
-- DCA (Dollar Cost Averaging) Tables Migration
-- Date: 2025-12-14
-- Description: Creates tables for DCA bot functionality
-- ============================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Table: dca_positions
-- Description: Tracks DCA positions (one position = multiple orders)
-- ============================================================================

CREATE TABLE IF NOT EXISTS dca_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    signal_id UUID REFERENCES trading_signals(id) ON DELETE SET NULL,
    
    -- Position details
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('long', 'short')),
    exchange VARCHAR(20) NOT NULL DEFAULT 'binance',
    
    -- DCA Configuration used
    base_order_percent FLOAT NOT NULL DEFAULT 40.0,
    safety_order_count INTEGER NOT NULL DEFAULT 3,
    safety_order_percent FLOAT NOT NULL DEFAULT 20.0,
    price_deviation_percent FLOAT NOT NULL DEFAULT 3.0,
    price_deviation_scale FLOAT NOT NULL DEFAULT 1.5,
    
    -- Aggregated values (updated on each fill)
    total_quantity FLOAT NOT NULL DEFAULT 0,
    average_entry_price FLOAT NOT NULL DEFAULT 0,
    total_invested FLOAT NOT NULL DEFAULT 0,
    filled_orders_count INTEGER NOT NULL DEFAULT 0,
    max_investment FLOAT,
    
    -- Targets (calculated from average price)
    take_profit_percent FLOAT NOT NULL DEFAULT 3.0,
    stop_loss_percent FLOAT NOT NULL DEFAULT 10.0,
    take_profit_price FLOAT,
    stop_loss_price FLOAT,
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'cancelled')),
    
    -- Results (filled when closed)
    exit_price FLOAT,
    realized_pnl FLOAT,
    realized_pnl_percent FLOAT,
    exit_reason VARCHAR(50),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for dca_positions
CREATE INDEX IF NOT EXISTS idx_dca_positions_user_id ON dca_positions(user_id);
CREATE INDEX IF NOT EXISTS idx_dca_positions_signal_id ON dca_positions(signal_id);
CREATE INDEX IF NOT EXISTS idx_dca_positions_symbol ON dca_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_dca_positions_status ON dca_positions(status);
CREATE INDEX IF NOT EXISTS idx_dca_positions_created_at ON dca_positions(created_at DESC);

-- ============================================================================
-- Table: dca_orders
-- Description: Individual orders within a DCA position
-- ============================================================================

CREATE TABLE IF NOT EXISTS dca_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dca_position_id UUID NOT NULL REFERENCES dca_positions(id) ON DELETE CASCADE,
    
    -- Order type
    order_type VARCHAR(20) NOT NULL,  -- 'base', 'safety_1', 'safety_2', etc.
    order_number INTEGER NOT NULL DEFAULT 0,  -- 0=base, 1=SO1, 2=SO2, etc.
    
    -- Trigger conditions
    trigger_price FLOAT NOT NULL,
    trigger_deviation_percent FLOAT,
    
    -- Order details
    target_quantity FLOAT NOT NULL,
    target_value FLOAT NOT NULL,
    
    -- Execution status
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'triggered', 'filled', 'cancelled', 'failed')),
    
    -- Fill details (populated when executed)
    fill_price FLOAT,
    fill_quantity FLOAT,
    fill_value FLOAT,
    fill_fee FLOAT,
    fill_time TIMESTAMP WITH TIME ZONE,
    
    -- Exchange order tracking
    exchange_order_id VARCHAR(100),
    exchange_order_status VARCHAR(50),
    
    -- Error tracking
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    triggered_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for dca_orders
CREATE INDEX IF NOT EXISTS idx_dca_orders_position_id ON dca_orders(dca_position_id);
CREATE INDEX IF NOT EXISTS idx_dca_orders_status ON dca_orders(status);
CREATE INDEX IF NOT EXISTS idx_dca_orders_order_type ON dca_orders(order_type);

-- ============================================================================
-- Table: dca_settings
-- Description: User-specific DCA configuration
-- ============================================================================

CREATE TABLE IF NOT EXISTS dca_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Enable/disable
    dca_enabled BOOLEAN NOT NULL DEFAULT false,
    
    -- Default DCA configuration
    default_base_order_percent FLOAT NOT NULL DEFAULT 40.0,
    default_safety_order_count INTEGER NOT NULL DEFAULT 3,
    default_safety_order_percent FLOAT NOT NULL DEFAULT 20.0,
    default_price_deviation_percent FLOAT NOT NULL DEFAULT 3.0,
    default_price_deviation_scale FLOAT NOT NULL DEFAULT 1.5,
    default_take_profit_percent FLOAT NOT NULL DEFAULT 3.0,
    default_stop_loss_percent FLOAT NOT NULL DEFAULT 10.0,
    
    -- Advanced settings
    max_active_dca_positions INTEGER NOT NULL DEFAULT 3,
    min_time_between_safety_orders INTEGER,  -- Seconds
    use_limit_orders BOOLEAN NOT NULL DEFAULT false,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Index for dca_settings
CREATE INDEX IF NOT EXISTS idx_dca_settings_user_id ON dca_settings(user_id);

-- ============================================================================
-- Triggers for updated_at
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for dca_positions
DROP TRIGGER IF EXISTS update_dca_positions_updated_at ON dca_positions;
CREATE TRIGGER update_dca_positions_updated_at
    BEFORE UPDATE ON dca_positions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for dca_settings
DROP TRIGGER IF EXISTS update_dca_settings_updated_at ON dca_settings;
CREATE TRIGGER update_dca_settings_updated_at
    BEFORE UPDATE ON dca_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Row Level Security (RLS) Policies
-- ============================================================================

-- Enable RLS on all DCA tables
ALTER TABLE dca_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE dca_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE dca_settings ENABLE ROW LEVEL SECURITY;

-- Policies for dca_positions
CREATE POLICY "Users can view their own DCA positions"
    ON dca_positions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own DCA positions"
    ON dca_positions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own DCA positions"
    ON dca_positions FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own DCA positions"
    ON dca_positions FOR DELETE
    USING (auth.uid() = user_id);

-- Policies for dca_orders (via dca_position ownership)
CREATE POLICY "Users can view their own DCA orders"
    ON dca_orders FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM dca_positions 
            WHERE dca_positions.id = dca_orders.dca_position_id 
            AND dca_positions.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert their own DCA orders"
    ON dca_orders FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM dca_positions 
            WHERE dca_positions.id = dca_orders.dca_position_id 
            AND dca_positions.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update their own DCA orders"
    ON dca_orders FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM dca_positions 
            WHERE dca_positions.id = dca_orders.dca_position_id 
            AND dca_positions.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete their own DCA orders"
    ON dca_orders FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM dca_positions 
            WHERE dca_positions.id = dca_orders.dca_position_id 
            AND dca_positions.user_id = auth.uid()
        )
    );

-- Policies for dca_settings
CREATE POLICY "Users can view their own DCA settings"
    ON dca_settings FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own DCA settings"
    ON dca_settings FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own DCA settings"
    ON dca_settings FOR UPDATE
    USING (auth.uid() = user_id);

-- ============================================================================
-- Service Role Policy (for bot backend)
-- ============================================================================

-- Allow service role to manage all DCA data (for bot operations)
CREATE POLICY "Service role can manage all DCA positions"
    ON dca_positions FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role can manage all DCA orders"
    ON dca_orders FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role can manage all DCA settings"
    ON dca_settings FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================================
-- Comments
-- ============================================================================

COMMENT ON TABLE dca_positions IS 'DCA (Dollar Cost Averaging) positions - tracks averaged entries with safety orders';
COMMENT ON TABLE dca_orders IS 'Individual orders within a DCA position (base order + safety orders)';
COMMENT ON TABLE dca_settings IS 'User-specific DCA configuration and preferences';

COMMENT ON COLUMN dca_positions.base_order_percent IS 'Percentage of total budget for initial entry (default 40%)';
COMMENT ON COLUMN dca_positions.safety_order_count IS 'Number of safety orders to place (default 3)';
COMMENT ON COLUMN dca_positions.price_deviation_percent IS 'Price drop percentage to trigger first safety order';
COMMENT ON COLUMN dca_positions.price_deviation_scale IS 'Multiplier for subsequent safety order deviations';
COMMENT ON COLUMN dca_positions.average_entry_price IS 'Volume-weighted average entry price across all filled orders';

COMMENT ON COLUMN dca_orders.order_type IS 'Type: base (initial), safety_1 (first safety), safety_2, etc.';
COMMENT ON COLUMN dca_orders.trigger_price IS 'Price at which this order should be triggered/executed';
COMMENT ON COLUMN dca_orders.status IS 'Order status: pending, triggered, filled, cancelled, failed';

-- ============================================================================
-- Verification Query
-- ============================================================================

-- Run this to verify tables were created successfully:
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'dca%';
