"""Promote a registered ``fraud-detector`` version to Production.

In MLflow 3.x the legacy ``Stage`` taxonomy was removed; we model the
``Production`` stage with the alias ``production`` plus a ``stage`` tag on
the model version. Pass ``--stage Production`` to keep parity with the
blueprint vocabulary; other stages are accepted but only ``Production``
flips the alias.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.core.logging import configure_logging  # noqa: E402
from src.models.registry import (  # noqa: E402
    PRODUCTION_ALIAS,
    MlflowRegistryClient,
)
from src.training.experiment import REGISTERED_MODEL_NAME, resolve_tracking_uri  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote a fraud-detector model version to Production"
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Model version to promote (string or int)",
    )
    parser.add_argument(
        "--stage",
        default="Production",
        help="Target stage label (default: Production). Maps to alias 'production'.",
    )
    parser.add_argument(
        "--model-name",
        default=REGISTERED_MODEL_NAME,
        help=f"Registered model name (default: {REGISTERED_MODEL_NAME})",
    )
    parser.add_argument(
        "--tracking-uri",
        default=None,
        help="Override MLflow tracking URI",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not tag previous Production versions as Archived",
    )
    return parser.parse_args()


def main() -> int:
    """Promote a model version and archive older Production versions."""
    configure_logging()
    args = _parse_args()

    tracking_uri = resolve_tracking_uri(args.tracking_uri)
    registry = MlflowRegistryClient(tracking_uri=tracking_uri)

    if args.stage.lower() != "production":
        logger.warning(
            "stage {!r} only tags the version; the {!r} alias is only set for 'Production'",
            args.stage,
            PRODUCTION_ALIAS,
        )
        registry.client.set_model_version_tag(
            name=args.model_name,
            version=str(args.version),
            key="stage",
            value=args.stage,
        )
    else:
        registry.promote_model_to_production(args.model_name, args.version)
        if not args.no_archive:
            registry.archive_old_versions(args.model_name, exclude_version=args.version)

    info = registry.get_production_model_info(args.model_name)
    if info is None:
        logger.warning(
            "no version of {!r} currently aliased {!r}",
            args.model_name,
            PRODUCTION_ALIAS,
        )
        return 1

    logger.info(
        "promotion complete | name={} version={} run_id={} aliases={} tags={}",
        info.name,
        info.version,
        info.run_id,
        info.aliases,
        info.tags,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
