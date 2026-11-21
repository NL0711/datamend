"""Telemetry stream: stored readings (with the source label) and the events the checks raised on them

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-21 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('stream_readings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('station_id', sa.String(length=64), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('temperature_c', sa.Float(), nullable=True),
    sa.Column('pressure_hpa', sa.Float(), nullable=True),
    sa.Column('humidity_pct', sa.Float(), nullable=True),
    sa.Column('rain_mm', sa.Float(), nullable=True),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('injected_fault', sa.String(length=40), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('check_status', sa.String(length=12), nullable=False),
    sa.Column('rule_score', sa.Float(), nullable=True),
    sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_stream_readings_station_time', 'stream_readings', ['station_id', 'timestamp'], unique=False)
    op.create_table('stream_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('reading_id', sa.Integer(), nullable=False),
    sa.Column('station_id', sa.String(length=64), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('variable', sa.String(length=16), nullable=False),
    sa.Column('verdict', sa.String(length=12), nullable=False),
    sa.Column('rule_score', sa.Float(), nullable=False),
    sa.Column('severity', sa.String(length=8), nullable=False),
    sa.Column('classification', sa.String(length=160), nullable=False),
    sa.Column('is_fault', sa.Boolean(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('hits', sa.JSON(), nullable=False),
    sa.Column('not_run', sa.JSON(), nullable=False),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['reading_id'], ['stream_readings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_stream_events_reading_id'), 'stream_events', ['reading_id'], unique=False)
    op.create_index(op.f('ix_stream_events_created_at'), 'stream_events', ['created_at'], unique=False)
    op.create_index('ix_stream_events_station_time', 'stream_events', ['station_id', 'timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_stream_events_station_time', table_name='stream_events')
    op.drop_index(op.f('ix_stream_events_created_at'), table_name='stream_events')
    op.drop_index(op.f('ix_stream_events_reading_id'), table_name='stream_events')
    op.drop_table('stream_events')
    op.drop_index('ix_stream_readings_station_time', table_name='stream_readings')
    op.drop_table('stream_readings')
