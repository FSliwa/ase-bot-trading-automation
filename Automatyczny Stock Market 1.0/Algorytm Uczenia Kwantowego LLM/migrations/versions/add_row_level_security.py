"""Add row level security policies

Revision ID: add_rls_001
Revises: 37d99c25f520
Create Date: 2025-09-17 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_rls_001'
down_revision = '37d99c25f520'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable RLS on all tables
    op.execute("""
        -- Enable RLS on users table
        ALTER TABLE users ENABLE ROW LEVEL SECURITY;
        
        -- Create role for authenticated users
        DO $$ BEGIN
            CREATE ROLE authenticated_users;
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        
        -- Policy for users table - users can only see their own data
        CREATE POLICY IF NOT EXISTS user_isolation_policy ON users
            FOR ALL
            USING (
                id = COALESCE(
                    current_setting('app.current_user_id', true)::integer,
                    -1
                )
            );
        
        -- Enable RLS on sessions table
        ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
        
        -- Policy for sessions - users can only see their own sessions
        CREATE POLICY IF NOT EXISTS session_isolation_policy ON sessions
            FOR ALL
            USING (
                user_id = COALESCE(
                    current_setting('app.current_user_id', true)::integer,
                    -1
                )
            );
        
        -- Enable RLS on trading_bots table
        ALTER TABLE trading_bots ENABLE ROW LEVEL SECURITY;
        
        -- Policy for trading_bots - users can only see their own bots
        CREATE POLICY IF NOT EXISTS trading_bot_isolation_policy ON trading_bots
            FOR ALL
            USING (
                user_id = COALESCE(
                    current_setting('app.current_user_id', true)::integer,
                    -1
                )
            );
        
        -- Enable RLS on transactions table
        ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
        
        -- Policy for transactions - users can only see their own transactions
        CREATE POLICY IF NOT EXISTS transaction_isolation_policy ON transactions
            FOR ALL
            USING (
                user_id = COALESCE(
                    current_setting('app.current_user_id', true)::integer,
                    -1
                )
            );
        
        -- Grant necessary permissions
        GRANT SELECT, INSERT, UPDATE, DELETE ON users TO authenticated_users;
        GRANT SELECT, INSERT, UPDATE, DELETE ON sessions TO authenticated_users;
        GRANT SELECT, INSERT, UPDATE, DELETE ON trading_bots TO authenticated_users;
        GRANT SELECT, INSERT, UPDATE, DELETE ON transactions TO authenticated_users;
    """)


def downgrade() -> None:
    # Disable RLS and remove policies
    op.execute("""
        -- Drop policies
        DROP POLICY IF EXISTS user_isolation_policy ON users;
        DROP POLICY IF EXISTS session_isolation_policy ON sessions;
        DROP POLICY IF EXISTS trading_bot_isolation_policy ON trading_bots;
        DROP POLICY IF EXISTS transaction_isolation_policy ON transactions;
        
        -- Disable RLS
        ALTER TABLE users DISABLE ROW LEVEL SECURITY;
        ALTER TABLE sessions DISABLE ROW LEVEL SECURITY;
        ALTER TABLE trading_bots DISABLE ROW LEVEL SECURITY;
        ALTER TABLE transactions DISABLE ROW LEVEL SECURITY;
        
        -- Revoke permissions
        REVOKE ALL ON users FROM authenticated_users;
        REVOKE ALL ON sessions FROM authenticated_users;
        REVOKE ALL ON trading_bots FROM authenticated_users;
        REVOKE ALL ON transactions FROM authenticated_users;
    """)
