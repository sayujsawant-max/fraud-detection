"""Drift-detection package.

Public entry points:

* :func:`load_reference_dataset` / :func:`build_current_dataset` — assemble
  the two DataFrames Evidently expects.
* :class:`DriftDetector` + :func:`run_drift_detection` — wrap the Evidently
  API call and translate the snapshot into a :class:`DriftDetectionResult`.
* :class:`DriftReportStore` — persist HTML/JSON artifacts under
  ``settings.DRIFT_REPORT_DIR``.

Keeping all of these out of ``src.api.routers`` is what lets Phase 6 reuse
them from Prefect flows without going through HTTP.
"""

from src.monitoring.data_loader import (
    build_current_dataset,
    load_prediction_log_rows,
    load_reference_dataset,
)
from src.monitoring.drift import (
    DriftDetectionResult,
    DriftDetector,
    evaluate_drift_threshold,
    extract_drift_metrics,
    run_drift_detection,
)
from src.monitoring.reports import DriftReportStore, generate_report_id

__all__ = [
    "DriftDetectionResult",
    "DriftDetector",
    "DriftReportStore",
    "build_current_dataset",
    "evaluate_drift_threshold",
    "extract_drift_metrics",
    "generate_report_id",
    "load_prediction_log_rows",
    "load_reference_dataset",
    "run_drift_detection",
]
