"""Add performance indexes

Revision ID: add_indexes_001
Revises: add_rls_001
Create Date: 2025-09-17 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_indexes_001'
down_revision = 'add_rls_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add covering indexes for common queries
    
    # Users table - email lookup with all needed fields
    op.create_index(
        'idx_users_email_active_covering',
        'users',
        ['email', 'is_active'],
        unique=False,
        postgresql_include=['id', 'username', 'password_hash', 'role', 'created_at', 'updated_at', 'last_login'],
        postgresql_concurrently=True,
        if_not_exists=True
    )
    
    # Users table - username lookup
    op.create_index(
        'idx_users_username_active',
        'users',
        ['username', 'is_active'],
        unique=False,
        postgresql_concurrently=True,
        if_not_exists=True
    )
    
    # Sessions table - token lookup with active sessions only
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_token_active 
        ON sessions(token) 
        WHERE expires_at > NOW()
    """)
    
    # Sessions table - user_id for session cleanup
    op.create_index(
        'idx_sessions_user_id_expires',
        'sessions',
        ['user_id', 'expires_at'],
        unique=False,
        postgresql_concurrently=True,
        if_not_exists=True
    )
    
    # Trading bots table - user's active bots
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trading_bots_user_active 
        ON trading_bots(user_id, is_active) 
        WHERE is_active = true
    """)
    
    # Transactions table - user transactions by date
    op.create_index(
        'idx_transactions_user_created',
        'transactions',
        ['user_id', 'created_at'],
        unique=False,
        postgresql_concurrently=True,
        if_not_exists=True
    )
    
    # Transactions table - by type for reporting
    op.create_index(
        'idx_transactions_type_status',
        'transactions',
        ['transaction_type', 'status'],
        unique=False,
        postgresql_concurrently=True,
        if_not_exists=True
    )
    
    # Add statistics update for better query planning
    op.execute("ANALYZE users, sessions, trading_bots, transactions;")


def downgrade() -> None:
    # Drop indexes in reverse order
    op.drop_index('idx_transactions_type_status', 'transactions', if_exists=True)
    op.drop_index('idx_transactions_user_created', 'transactions', if_exists=True)
    op.drop_index('idx_trading_bots_user_active', 'trading_bots', if_exists=True)
    op.drop_index('idx_sessions_user_id_expires', 'sessions', if_exists=True)
    op.drop_index('idx_sessions_token_active', 'sessions', if_exists=True)
    op.drop_index('idx_users_username_active', 'users', if_exists=True)
    op.drop_index('idx_users_email_active_covering', 'users', if_exists=True)
