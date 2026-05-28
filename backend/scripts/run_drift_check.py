"""Run a one-shot Evidently drift check from the command line.

Reads the reference parquet, pulls the most recent prediction logs from
PostgreSQL via SQLAlchemy *sync*, computes drift, writes HTML/JSON
artifacts under ``DRIFT_REPORT_DIR``, and inserts one row into
``drift_reports``.

Use this for ad-hoc runs or as the worker the Phase 6 Prefect flow will
schedule. Run from project root:

.. code-block:: bash

   python backend/scripts/run_drift_check.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd  # noqa: E402
from loguru import logger  # noqa: E402
from sqlalchemy import create_engine, desc, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.exceptions import DriftDataError, DriftError  # noqa: E402
from src.db.models.drift_report import DriftReport  # noqa: E402
from src.db.models.prediction import PredictionLog  # noqa: E402
from src.features.constants import TARGET_COLUMN  # noqa: E402
from src.monitoring.drift import (  # noqa: E402
    DriftDetector,
    evaluate_drift_threshold,
    extract_drift_metrics,
)
from src.monitoring.reports import DriftReportStore, generate_report_id  # noqa: E402

REFERENCE_FALLBACK = "backend/data/raw/train.parquet"
REFERENCE_FALLBACK_SAMPLE_SIZE = 5000


def _resolve_path(path_like: str) -> Path:
    """Resolve a settings path string into an absolute :class:`Path`."""
    direct = Path(path_like)
    if direct.exists():
        return direct.resolve()
    if path_like.startswith("backend/"):
        stripped = Path(path_like[len("backend/") :])
        if stripped.exists():
            return stripped.resolve()
    for parent in Path.cwd().resolve().parents:
        candidate = parent / path_like
        if candidate.exists():
            return candidate.resolve()
    return direct.resolve()


def _load_reference(settings: Any) -> pd.DataFrame:
    ref_path = _resolve_path(settings.REFERENCE_DATA_PATH)
    if ref_path.exists():
        logger.info("loading reference dataset from {}", ref_path)
        df = pd.read_parquet(ref_path)
    else:
        fallback = _resolve_path(REFERENCE_FALLBACK)
        if not fallback.exists():
            raise DriftDataError(
                f"Reference dataset not found at {ref_path} and fallback "
                f"{fallback} is also missing. Run `make generate-data` first."
            )
        logger.warning("reference missing; falling back to {}", fallback)
        df = pd.read_parquet(fallback).head(REFERENCE_FALLBACK_SAMPLE_SIZE)
    if TARGET_COLUMN in df.columns:
        df = df.drop(columns=[TARGET_COLUMN])
    return df.reset_index(drop=True)


def _load_current(
    session: Session, limit: int
) -> tuple[pd.DataFrame, list[PredictionLog]]:
    rows = list(
        session.execute(
            select(PredictionLog).order_by(desc(PredictionLog.timestamp)).limit(limit)
        )
        .scalars()
        .all()
    )
    records = [
        dict(row.input_features) for row in rows if isinstance(row.input_features, dict)
    ]
    df = pd.DataFrame.from_records(records)
    if TARGET_COLUMN in df.columns:
        df = df.drop(columns=[TARGET_COLUMN])
    return df, rows


def main() -> int:
    """Entrypoint — returns the process exit code."""
    settings = get_settings()
    engine = create_engine(settings.database_url_sync, future=True)
    try:
        reference_df = _load_reference(settings)
        with Session(engine) as session:
            current_df, rows = _load_current(session, settings.DRIFT_LOOKBACK_LIMIT)

            if len(current_df) < settings.DRIFT_MIN_SAMPLES:
                logger.warning(
                    "insufficient prediction logs | {} < min_samples={}",
                    len(current_df),
                    settings.DRIFT_MIN_SAMPLES,
                )
                session.add(
                    DriftReport(
                        id=uuid.uuid4(),
                        report_id=generate_report_id(),
                        drift_detected=False,
                        num_samples=len(current_df),
                        status="skipped",
                        reason="insufficient_prediction_logs",
                        reference_dataset_path=settings.REFERENCE_DATA_PATH,
                    )
                )
                session.commit()
                return 0

            # Align current to reference columns to avoid Evidently mismatch.
            for col in reference_df.columns:
                if col not in current_df.columns:
                    current_df[col] = pd.NA
            current_df = current_df.loc[:, list(reference_df.columns)]

            detector = DriftDetector(settings)
            snapshot = detector.run(reference_df, current_df)
            report_json = snapshot.dict()
            metrics = extract_drift_metrics(report_json)
            drift_score = metrics["drift_score"]
            drift_detected = evaluate_drift_threshold(
                drift_score, settings.DRIFT_THRESHOLD
            )

            store = DriftReportStore(settings)
            report_id = generate_report_id()
            html_path, json_path = store.paths_for(report_id)
            detector.save_artifacts(snapshot, html_path, json_path)

            generated_at = datetime.now(tz=UTC)
            session.add(
                DriftReport(
                    id=uuid.uuid4(),
                    report_id=report_id,
                    generated_at=generated_at,
                    drift_detected=drift_detected,
                    drift_score=drift_score,
                    num_drifted_features=metrics["num_drifted_features"],
                    total_features=metrics["total_features"],
                    num_samples=int(len(current_df)),
                    reference_dataset_path=settings.REFERENCE_DATA_PATH,
                    current_window_start=rows[-1].timestamp if rows else None,
                    current_window_end=rows[0].timestamp if rows else None,
                    report_html_path=str(html_path),
                    report_json_path=str(json_path),
                    report_json=report_json,
                    status="complete",
                )
            )
            session.commit()

        logger.info(
            "drift check complete | id={} drifted={} score={} html={}",
            report_id,
            drift_detected,
            drift_score,
            html_path,
        )
        return 0
    except DriftError as exc:
        logger.error("drift run failed: {}", exc)
        return 1
    except DriftDataError as exc:
        logger.error("drift data error: {}", exc)
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
