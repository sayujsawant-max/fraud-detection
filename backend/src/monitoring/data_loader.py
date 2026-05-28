"""Helpers that assemble the two DataFrames Evidently compares.

* :func:`load_reference_dataset` reads ``reference.parquet`` — the training
  snapshot we treat as the drift baseline. Falls back to
  ``data/raw/train.parquet[:5000]`` when the dedicated reference file is
  missing, and raises :class:`DriftDataError` with a clear remediation hint
  when neither exists.
* :func:`load_prediction_log_rows` pulls the most recent N prediction-log
  rows out of PostgreSQL via the repository layer.
* :func:`build_current_dataset` flattens those rows into a DataFrame whose
  columns line up with the reference dataset, so Evidently can compute
  per-column drift without any column-mismatch surprises.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.exceptions import DriftDataError
from src.db.models.prediction import PredictionLog
from src.db.repositories import PredictionLogRepository
from src.features.constants import FEATURE_COLUMNS, TARGET_COLUMN

REFERENCE_FALLBACK_PATH: str = "backend/data/raw/train.parquet"
REFERENCE_FALLBACK_SAMPLE_SIZE: int = 5000


def _resolve_path(path_like: str) -> Path:
    """Resolve a settings path string into an absolute :class:`Path`.

    Settings paths are relative to the *project root* (one level up from
    ``backend/``). We try the path as-given first, then fall back to the
    backend-anchored form so the same value works whether the process was
    launched from the project root or from ``backend/``.
    """
    direct = Path(path_like)
    if direct.exists():
        return direct.resolve()

    # If we're already inside backend/, the ``backend/...`` prefix is
    # redundant — strip it and try the relative form too.
    if path_like.startswith("backend/"):
        stripped = Path(path_like[len("backend/") :])
        if stripped.exists():
            return stripped.resolve()

    # Last resort: walk up looking for a sibling ``backend`` directory.
    for parent in Path.cwd().resolve().parents:
        candidate = parent / path_like
        if candidate.exists():
            return candidate.resolve()
    return direct.resolve()


def load_reference_dataset(settings: Settings) -> pd.DataFrame:
    """Return the reference DataFrame used as the drift baseline.

    The reference file is the training snapshot captured in Phase 1. It is
    not regenerated on every prediction — that would defeat the whole
    purpose of drift detection. When the file is missing we fall back to a
    deterministic head() over ``train.parquet`` so local-dev demos work
    out-of-the-box; production deployments should always have a real
    reference file checked in.

    The ``is_fraud`` target column is dropped before return because
    prediction logs do not carry ground truth.
    """
    ref_path = _resolve_path(settings.REFERENCE_DATA_PATH)
    if ref_path.exists():
        logger.info("loading reference dataset from {}", ref_path)
        df = pd.read_parquet(ref_path)
    else:
        fallback = _resolve_path(REFERENCE_FALLBACK_PATH)
        if not fallback.exists():
            raise DriftDataError(
                f"Reference dataset not found at {ref_path} and fallback "
                f"{fallback} is also missing. Run `make generate-data` first."
            )
        logger.warning(
            "reference dataset missing at {} — falling back to first {} rows of {}",
            ref_path,
            REFERENCE_FALLBACK_SAMPLE_SIZE,
            fallback,
        )
        df = pd.read_parquet(fallback).head(REFERENCE_FALLBACK_SAMPLE_SIZE)

    if TARGET_COLUMN in df.columns:
        df = df.drop(columns=[TARGET_COLUMN])
    return df.reset_index(drop=True)


async def load_prediction_log_rows(
    session: AsyncSession, limit: int
) -> list[PredictionLog]:
    """Fetch the most recent ``limit`` prediction-log rows."""
    repo = PredictionLogRepository(session)
    rows, _total = await repo.list_logs(limit=limit, offset=0)
    return rows


def build_current_dataset(
    rows: list[PredictionLog],
    reference_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Reconstruct a feature DataFrame from a list of :class:`PredictionLog`.

    The ``input_features`` JSONB column already stores everything the
    pipeline saw at predict-time, so we just unpack it back into a frame.
    We then conform to ``reference_columns`` (when given) so the two frames
    Evidently sees have an identical schema — Evidently rejects unaligned
    columns with an opaque error otherwise.
    """
    if not rows:
        # Build an empty frame with the right column shape so downstream
        # callers can still introspect ``.columns`` without crashing.
        cols = reference_columns or FEATURE_COLUMNS
        return pd.DataFrame(columns=cols)

    records: list[dict[str, Any]] = []
    for row in rows:
        # ``input_features`` should always be a dict — but JSONB can be
        # ``None`` on a manually-inserted row. Guard so a single bad record
        # doesn't poison the whole window.
        if isinstance(row.input_features, dict):
            records.append(dict(row.input_features))
        else:
            logger.warning(
                "skipping prediction_log with non-dict input_features | id={} type={}",
                row.id,
                type(row.input_features).__name__,
            )

    if not records:
        cols = reference_columns or FEATURE_COLUMNS
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame.from_records(records)

    if reference_columns is not None:
        # Restrict to the reference's column set; fill in any missing
        # columns with NaN so Evidently sees a consistent shape.
        for col in reference_columns:
            if col not in df.columns:
                df[col] = pd.NA
        df = df.loc[:, list(reference_columns)]
    elif TARGET_COLUMN in df.columns:
        df = df.drop(columns=[TARGET_COLUMN])

    return df.reset_index(drop=True)
