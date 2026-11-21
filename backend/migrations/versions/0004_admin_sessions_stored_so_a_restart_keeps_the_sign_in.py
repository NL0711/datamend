"""admin sessions stored in the database (token hash only), so a restart keeps the sign-in

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-21 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('admin_sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('token_hash'))
    op.create_index(op.f('ix_admin_sessions_expires_at'), 'admin_sessions', ['expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_admin_sessions_expires_at'), table_name='admin_sessions')
    op.drop_table('admin_sessions')
