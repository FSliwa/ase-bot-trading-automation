-- Migration: Create API key and trade order tables

CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exchange VARCHAR(64) NOT NULL,
    access_key VARCHAR(255) NOT NULL,
    secret_key VARCHAR(255) NOT NULL,
    passphrase VARCHAR(255),
    label VARCHAR(120),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_api_keys_user_exchange UNIQUE (user_id, exchange)
);

CREATE INDEX IF NOT EXISTS ix_api_keys_user_exchange ON api_keys (user_id, exchange);

CREATE TABLE IF NOT EXISTS trade_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exchange VARCHAR(64) NOT NULL,
    symbol VARCHAR(120) NOT NULL,
    side VARCHAR(8) NOT NULL,
    order_type VARCHAR(16) NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    executed_quantity DOUBLE PRECISION,
    price DOUBLE PRECISION,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    external_id VARCHAR(255),
    raw_response JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_trade_orders_user_exchange ON trade_orders (user_id, exchange);
CREATE INDEX IF NOT EXISTS ix_trade_orders_external_id ON trade_orders (external_id);
