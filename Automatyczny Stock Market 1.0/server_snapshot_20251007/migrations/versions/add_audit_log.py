"""Add audit log table

Revision ID: add_audit_001
Revises: add_indexes_001
Create Date: 2025-09-17 17:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_audit_001'
down_revision = 'add_indexes_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create audit log table
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource', sa.String(100), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('severity', sa.String(20), nullable=False, server_default='INFO'),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    )
    
    # Create indexes for audit log
    op.create_index('idx_audit_log_user_timestamp', 'audit_log', ['user_id', 'timestamp'])
    op.create_index('idx_audit_log_action', 'audit_log', ['action'])
    op.create_index('idx_audit_log_timestamp', 'audit_log', ['timestamp'])
    op.create_index('idx_audit_log_severity', 'audit_log', ['severity'])
    
    # Create partial index for failed actions
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_log_failed_actions 
        ON audit_log(timestamp, action) 
        WHERE success = false
    """)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_audit_log_failed_actions', 'audit_log', if_exists=True)
    op.drop_index('idx_audit_log_severity', 'audit_log', if_exists=True)
    op.drop_index('idx_audit_log_timestamp', 'audit_log', if_exists=True)
    op.drop_index('idx_audit_log_action', 'audit_log', if_exists=True)
    op.drop_index('idx_audit_log_user_timestamp', 'audit_log', if_exists=True)
    
    # Drop table
    op.drop_table('audit_log')
