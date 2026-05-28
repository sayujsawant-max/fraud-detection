"""Alembic environment configuration for FraudShield.

This module wires Alembic to the project's :class:`Settings` so migrations
run against whatever ``DATABASE_URL`` the operator sets in ``.env``. We
also import the ORM models so autogenerate sees every table without each
new model having to register itself in the migration script.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make ``src.*`` importable when alembic is invoked from the ``backend``
# directory (which is what ``alembic.ini``'s ``prepend_sys_path = .``
# already arranges, but we do it again here so this env.py also works when
# someone runs alembic from project root).
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import src.db.models  # noqa: F401,E402  — registers tables on Base.metadata
from src.core.config import get_settings  # noqa: E402  (post sys.path mutation)
from src.db.base import Base  # noqa: E402

# This is the Alembic Config object, which provides access to the values
# within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use the sync URL — Alembic does not run inside an async event loop.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no DB connection — emits SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
