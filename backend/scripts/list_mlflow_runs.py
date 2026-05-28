"""List recent runs from the FraudShield MLflow experiment.

Connects to the tracking server, fetches the most recent runs from the
``fraud-detection`` experiment (overridable via ``--experiment-name``),
and logs a tabular summary using Loguru — no ``print`` calls.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import mlflow
from loguru import logger
from mlflow.tracking import MlflowClient

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.core.logging import configure_logging  # noqa: E402
from src.training.experiment import EXPERIMENT_NAME, resolve_tracking_uri  # noqa: E402

_HEADER = "{:<32} {:<22} {:>8} {:>8} {:>8} {:<10}".format(
    "run_id", "model_type", "pr_auc", "roc_auc", "f1", "status"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List recent MLflow runs")
    parser.add_argument(
        "--experiment-name",
        default=EXPERIMENT_NAME,
        help=f"Experiment to list (default: {EXPERIMENT_NAME})",
    )
    parser.add_argument(
        "--tracking-uri",
        default=None,
        help="Override MLflow tracking URI",
    )
    parser.add_argument(
        "--limit", type=int, default=20, help="Maximum runs to list (default: 20)"
    )
    return parser.parse_args()


def main() -> int:
    """List the most recent runs from the chosen experiment."""
    configure_logging()
    args = _parse_args()

    tracking_uri = resolve_tracking_uri(args.tracking_uri)
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)

    experiment = client.get_experiment_by_name(args.experiment_name)
    if experiment is None:
        logger.error(
            "experiment {!r} not found on {} — run train-mlflow first",
            args.experiment_name,
            tracking_uri,
        )
        return 1

    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["attributes.start_time DESC"],
        max_results=args.limit,
    )
    if not runs:
        logger.info("no runs found in {!r}", args.experiment_name)
        return 0

    logger.info("recent runs in {!r} ({} shown):", args.experiment_name, len(runs))
    logger.info(_HEADER)
    for run in runs:
        metrics = run.data.metrics
        tags = run.data.tags
        row = "{run_id:<32} {model_type:<22} {pr_auc:>8} {roc_auc:>8} {f1:>8} {status:<10}".format(
            run_id=run.info.run_id,
            model_type=tags.get("model_type", "-")[:22],
            pr_auc=f"{metrics.get('pr_auc', float('nan')):.4f}",
            roc_auc=f"{metrics.get('roc_auc', float('nan')):.4f}",
            f1=f"{metrics.get('f1_score', float('nan')):.4f}",
            status=run.info.status,
        )
        logger.info(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
