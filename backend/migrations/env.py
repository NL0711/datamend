"""Alembic environment: the same tables as the app (Base.metadata), the same database URL as the app (DATABASE_URL, async driver), portable
between SQLite and PostgreSQL (batch mode on SQLite so a column change works there too)."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.config import settings
from backend.app.db.database import Base
from backend.app.pipeline import models as _pipeline_models  # noqa: F401  (registers the tables)
from backend.app.stream import models as _stream_models  # noqa: F401
from backend.app.agent import models as _agent_models  # noqa: F401
from backend.app.validation import models as _validation_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata
URL = settings.DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True, render_as_batch=URL.startswith("sqlite"))
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=URL.startswith("sqlite"), compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(URL)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
