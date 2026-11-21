"""Agent event log (append-only), tasks and proposals

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-21 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('agent_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('task_id', sa.String(length=64), nullable=False),
    sa.Column('step', sa.Integer(), nullable=False),
    sa.Column('node', sa.String(length=24), nullable=False),
    sa.Column('record', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_agent_events_task_step', 'agent_events', ['task_id', 'step'], unique=False)
    op.create_table('agent_tasks',
    sa.Column('task_id', sa.String(length=64), nullable=False),
    sa.Column('station_id', sa.String(length=64), nullable=False),
    sa.Column('request', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('task_id'))
    op.create_index(op.f('ix_agent_tasks_station_id'), 'agent_tasks', ['station_id'], unique=False)
    op.create_table('agent_proposals',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('task_id', sa.String(length=64), nullable=False),
    sa.Column('action', sa.String(length=32), nullable=False),
    sa.Column('station_id', sa.String(length=64), nullable=True),
    sa.Column('run_id', sa.Integer(), nullable=True),
    sa.Column('row_ref', sa.String(length=64), nullable=True),
    sa.Column('args', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('review_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_agent_proposals_task_id'), 'agent_proposals', ['task_id'], unique=False)
    op.create_index(op.f('ix_agent_proposals_station_id'), 'agent_proposals', ['station_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_proposals_station_id'), table_name='agent_proposals')
    op.drop_index(op.f('ix_agent_proposals_task_id'), table_name='agent_proposals')
    op.drop_table('agent_proposals')
    op.drop_index(op.f('ix_agent_tasks_station_id'), table_name='agent_tasks')
    op.drop_table('agent_tasks')
    op.drop_index('ix_agent_events_task_step', table_name='agent_events')
    op.drop_table('agent_events')
