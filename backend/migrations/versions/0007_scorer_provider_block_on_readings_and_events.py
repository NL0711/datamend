"""Keras scorer: a nullable JSON provider block on stream readings and events

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-21 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('stream_readings', sa.Column('provider', sa.JSON(), nullable=True))
    op.add_column('stream_events', sa.Column('provider', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('stream_events', 'provider')
    op.drop_column('stream_readings', 'provider')
