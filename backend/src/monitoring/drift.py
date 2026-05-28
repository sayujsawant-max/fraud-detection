"""Evidently AI drift wrapper + result types.

This module is the single place that talks to Evidently. The Evidently 0.7
API uses ``Report(metrics=[DataDriftPreset()])`` plus ``report.run(reference_data, current_data)``
which returns a ``Snapshot`` exposing ``dict()``, ``json()``, ``save_html()``,
and ``save_json()``. Earlier 0.4.x versions exposed ``Report`` directly
without the ``Snapshot`` indirection; if you ever upgrade and the surface
changes again, only :class:`DriftDetector` should need touching.

Defensive parsing: the Evidently JSON layout has shifted between versions
and within metrics, so :func:`extract_drift_metrics` walks the structure
key-by-key with ``.get(...)`` fallbacks and never raises on a missing
nested field — it just returns ``None`` for the unknown metric so the
caller can decide whether that counts as a failure.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
from loguru import logger

from src.core.config import Settings, get_settings
from src.core.exceptions import DriftError

if TYPE_CHECKING:
    from evidently.core.report import Snapshot


# The DriftedColumnsCount metric in Evidently 0.7 is the one that exposes
# {"count": N, "share": float}. Matching by substring keeps us robust to
# Evidently appending parametrisation to the metric_name string.
_DRIFTED_COLUMNS_METRIC_KEY: str = "DriftedColumnsCount"
_VALUE_DRIFT_METRIC_KEY: str = "ValueDrift"


@dataclass
class DriftDetectionResult:
    """In-process result of one drift run.

    Mirrors the JSON returned by ``POST /v1/monitoring/drift/check`` so the
    router can build the response with a single ``asdict`` call.
    """

    status: str = "complete"  # "complete" | "skipped" | "failed"
    drift_detected: bool = False
    drift_score: float | None = None
    num_drifted_features: int | None = None
    total_features: int | None = None
    num_samples: int = 0
    report_id: str | None = None
    report_html_path: str | None = None
    report_json_path: str | None = None
    report_json: dict[str, Any] | None = None
    reason: str | None = None
    reference_dataset_path: str | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    current_window_start: datetime | None = None
    current_window_end: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a plain-dict view safe for JSON serialisation."""
        return asdict(self)


def evaluate_drift_threshold(drift_score: float | None, threshold: float) -> bool:
    """Return True when ``drift_score`` exceeds ``threshold``.

    ``None`` short-circuits to False — we cannot claim drift on a missing
    measurement. Equality goes to False because Evidently's share is a
    continuous quantity and ``>`` is the convention in the blueprint.
    """
    if drift_score is None:
        return False
    return float(drift_score) > float(threshold)


def extract_drift_metrics(report_json: dict[str, Any] | None) -> dict[str, Any]:
    """Pull the headline metrics out of a Snapshot's ``dict()`` output.

    Returns a dict with keys:

    * ``drift_score`` — share of drifted columns (0.0–1.0) or ``None``
    * ``num_drifted_features`` — count of columns flagged as drifted
    * ``total_features`` — total feature-drift metrics in the report
    * ``per_column_drift`` — best-effort ``{column: drift_value}`` map

    The function is intentionally tolerant of missing keys so the caller
    can decide what to do; it never raises on a malformed report.
    """
    out: dict[str, Any] = {
        "drift_score": None,
        "num_drifted_features": None,
        "total_features": None,
        "per_column_drift": {},
    }
    if not isinstance(report_json, dict):
        return out

    metrics = report_json.get("metrics")
    if not isinstance(metrics, list):
        return out

    per_column: dict[str, Any] = {}
    value_drift_count = 0
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        name = metric.get("metric_name") or metric.get("metric_id") or ""

        if _DRIFTED_COLUMNS_METRIC_KEY in name:
            value = metric.get("value")
            if isinstance(value, dict):
                share = value.get("share")
                count = value.get("count")
                if share is not None:
                    out["drift_score"] = float(share)
                if count is not None:
                    out["num_drifted_features"] = int(count)
            elif isinstance(value, int | float):
                out["drift_score"] = float(value)

        elif _VALUE_DRIFT_METRIC_KEY in name:
            value_drift_count += 1
            # ``column=<name>`` is embedded in the metric_name string. The
            # Evidently config dict also carries it explicitly — prefer that
            # when present.
            config = metric.get("config") or {}
            col = config.get("column")
            if not col and "column=" in name:
                # name format: "ValueDrift(column=amount,method=K-S p_value,...)"
                try:
                    fragment = name.split("column=", 1)[1]
                    col = fragment.split(",", 1)[0].strip(") ")
                except IndexError:
                    col = None
            if col:
                per_column[str(col)] = metric.get("value")

    if value_drift_count:
        out["total_features"] = value_drift_count
    out["per_column_drift"] = per_column
    return out


class DriftDetector:
    """Run Evidently DataDriftPreset and translate the snapshot.

    The class doesn't hold state between calls — it exists so the Evidently
    import is contained to one module and so tests can patch a single
    target (``DriftDetector.run``) instead of monkey-patching ``evidently``.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def threshold(self) -> float:
        return float(self._settings.DRIFT_THRESHOLD)

    def run(
        self,
        reference_df: pd.DataFrame,
        current_df: pd.DataFrame,
    ) -> Snapshot:
        """Execute the Evidently report and return the raw Snapshot.

        We import Evidently lazily so unit tests that mock this method
        don't pay the (substantial) Evidently import time.
        """
        try:
            from evidently import Dataset, Report
            from evidently.presets import DataDriftPreset
        except ImportError as exc:  # pragma: no cover — install error
            raise DriftError(
                "Evidently AI is not installed — `pip install evidently`."
            ) from exc

        if reference_df.empty or current_df.empty:
            raise DriftError("reference_df and current_df must both be non-empty")

        try:
            ref_ds = Dataset.from_pandas(reference_df)
            cur_ds = Dataset.from_pandas(current_df)
            report = Report(metrics=[DataDriftPreset()])
            snapshot = report.run(reference_data=ref_ds, current_data=cur_ds)
        except Exception as exc:  # noqa: BLE001 — wrap any Evidently error
            logger.exception("Evidently report run failed: {}", exc)
            raise DriftError(f"Evidently failed to compute drift: {exc}") from exc
        return snapshot

    def save_artifacts(
        self,
        snapshot: Snapshot,
        html_path: Path,
        json_path: Path,
    ) -> None:
        """Persist the snapshot to disk as HTML + JSON.

        Both paths must already include the desired filename; the parent
        directory is created on demand so callers don't have to mkdir.
        """
        html_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            snapshot.save_html(str(html_path))
            snapshot.save_json(str(json_path))
        except Exception as exc:  # noqa: BLE001
            logger.exception("failed to persist drift report artifacts: {}", exc)
            raise DriftError("failed to save drift report artifacts") from exc


def run_drift_detection(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    *,
    settings: Settings | None = None,
    detector: DriftDetector | None = None,
) -> tuple[DriftDetectionResult, Snapshot | None]:
    """Convenience: run the detector and translate the snapshot in one call.

    Returns ``(result, snapshot)``. The snapshot is exposed so the caller
    can persist artifacts; passing it back instead of inlining the save
    here lets tests skip disk I/O.
    """
    settings = settings or get_settings()
    detector = detector or DriftDetector(settings)

    snapshot = detector.run(reference_df, current_df)
    report_json = snapshot.dict()
    metrics = extract_drift_metrics(report_json)
    drift_score = metrics["drift_score"]
    drift_detected = evaluate_drift_threshold(drift_score, settings.DRIFT_THRESHOLD)

    result = DriftDetectionResult(
        status="complete",
        drift_detected=drift_detected,
        drift_score=drift_score,
        num_drifted_features=metrics["num_drifted_features"],
        total_features=metrics["total_features"],
        num_samples=int(len(current_df)),
        report_json=report_json,
    )
    return result, snapshot
