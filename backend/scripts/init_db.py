"""Initialise the FraudShield database.

Runs ``alembic upgrade head`` against the configured ``DATABASE_URL``. If
Alembic is not installed (e.g. in a minimal CI image) we fall back to
``Base.metadata.create_all`` — useful for local SQLite smoke tests but not
production.

Run from project root:

.. code-block:: bash

   python backend/scripts/init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``src.*`` importable when running from project root or anywhere else.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from loguru import logger  # noqa: E402

import src.db.models  # noqa: F401,E402  — registers tables on Base.metadata
from src.core.config import get_settings  # noqa: E402
from src.db.base import Base  # noqa: E402


def _alembic_upgrade_head() -> bool:
    """Run ``alembic upgrade head`` via the Python API.

    Returns True on success, False if Alembic itself can't be imported.
    """
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        logger.warning("alembic not installed — falling back to create_all")
        return False

    ini_path = BACKEND_DIR / "alembic.ini"
    if not ini_path.exists():
        logger.warning("alembic.ini not found at {} — falling back", ini_path)
        return False

    cfg = Config(str(ini_path))
    # Make sure Alembic looks at the right scripts directory even when the
    # CWD isn't ``backend/``.
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    logger.info("running alembic upgrade head | ini={}", ini_path)
    command.upgrade(cfg, "head")
    return True


def _create_all_fallback() -> None:
    """Last-resort ``Base.metadata.create_all`` for environments without Alembic."""
    from sqlalchemy import create_engine

    settings = get_settings()
    engine = create_engine(settings.database_url_sync, future=True)
    logger.info("creating tables via Base.metadata.create_all")
    Base.metadata.create_all(engine)
    engine.dispose()


def main() -> None:
    """Entrypoint."""
    settings = get_settings()
    logger.info(
        "initialising database | env={} | driver={}",
        settings.ENVIRONMENT,
        settings.database_url_sync.split("://", 1)[0],
    )
    if not _alembic_upgrade_head():
        _create_all_fallback()
    logger.info("database initialisation complete")


if __name__ == "__main__":
    main()
