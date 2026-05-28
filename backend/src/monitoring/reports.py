"""Drift report storage helpers.

The store is intentionally dumb: filesystem layout is

::

    settings.DRIFT_REPORT_DIR /
        drift_YYYYMMDD_HHMMSS.html
        drift_YYYYMMDD_HHMMSS.json

The ``report_id`` is the basename (``drift_YYYYMMDD_HHMMSS``); the
``DriftReport`` row in the database stores both the id and the absolute
paths so the API can ``FileResponse`` the HTML back to clients without
re-deriving the location.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from src.core.config import Settings, get_settings

REPORT_ID_FORMAT: str = "drift_%Y%m%d_%H%M%S"


def generate_report_id(now: datetime | None = None) -> str:
    """Return a filename-safe id based on UTC timestamp."""
    timestamp = now or datetime.now(tz=UTC)
    # ``%f`` adds microseconds so two runs in the same second don't collide.
    return timestamp.strftime(REPORT_ID_FORMAT) + f"_{timestamp.microsecond:06d}"


class DriftReportStore:
    """Filesystem persistence for Evidently HTML/JSON artifacts.

    The store does **not** touch the database — that belongs to
    :class:`DriftReportRepository`. Splitting them lets the Phase 6 Prefect
    flow drop a report on disk first (idempotent) and only then commit a
    Postgres row.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def base_dir(self) -> Path:
        """Resolve ``DRIFT_REPORT_DIR`` to an absolute :class:`Path`.

        Same project-root resolution as :mod:`data_loader` — the value in
        settings is relative to the repo root so it works whether the
        process was launched from there or from ``backend/``.
        """
        path_like = self._settings.DRIFT_REPORT_DIR
        direct = Path(path_like)
        if direct.is_absolute():
            return direct

        # Prefer the path as given when its parent exists.
        if direct.parent.exists():
            return direct.resolve()

        if path_like.startswith("backend/"):
            stripped = Path(path_like[len("backend/") :])
            if stripped.parent.exists():
                return stripped.resolve()

        for parent in Path.cwd().resolve().parents:
            candidate = parent / path_like
            if candidate.parent.exists():
                return candidate.resolve()

        return direct.resolve()

    def ensure_directory(self) -> Path:
        """Create the base directory (idempotent) and return it."""
        path = self.base_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def paths_for(self, report_id: str) -> tuple[Path, Path]:
        """Return ``(html_path, json_path)`` for a given id.

        Files do not need to exist yet — this is the canonical naming
        convention the rest of the layer relies on.
        """
        directory = self.ensure_directory()
        return (directory / f"{report_id}.html", directory / f"{report_id}.json")

    def html_path(self, report_id: str) -> Path:
        """Filesystem location of an HTML report (may or may not exist)."""
        return self.paths_for(report_id)[0]

    def json_path(self, report_id: str) -> Path:
        """Filesystem location of a JSON report (may or may not exist)."""
        return self.paths_for(report_id)[1]

    def cleanup_partial(self, report_id: str) -> None:
        """Best-effort delete of half-written artifacts."""
        for path in self.paths_for(report_id):
            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:  # pragma: no cover — cleanup failure
                logger.warning("failed to unlink {}: {}", path, exc)
