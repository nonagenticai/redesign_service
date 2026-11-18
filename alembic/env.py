"""Alembic configuration for redesign_service (sync migrations via psycopg v3).

Migrations are the ONLY thing that creates schema in this service. The app used
to call `Base.metadata.create_all` in its lifespan, which left `alembic_version`
empty while the tables already existed, so `alembic upgrade head` would then hit
001_initial_schema's CREATE TABLE and fail. That call has been removed; alembic
owns the schema.

`script_location` in alembic.ini previously pointed at src/database/migrations,
whose versions/ was empty, while the three real revisions sat in this directory
unread. `alembic heads` reported nothing and `alembic upgrade head` applied zero
migrations. Both now point here.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Repo root on sys.path so `from src.database.models import Base` resolves.
# `alembic heads` does not execute env.py, but `upgrade`/`revision` do.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from src.database.models import Base  # noqa: E402

target_metadata = Base.metadata


def get_url() -> str:
    """Resolve the URL migrations run against.

    The archetype sets DATABASE_URL to its per-job ephemeral postgres:18
    container, so CI never falls through to the alembic.ini placeholder.
    Fleet standard is psycopg v3, so a bare postgresql:// URL is normalised
    to postgresql+psycopg://.
    """
    url = os.getenv("MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "no database URL configured for alembic; set DATABASE_URL "
            "(or MIGRATION_DATABASE_URL for a separate owner role)."
        )
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
