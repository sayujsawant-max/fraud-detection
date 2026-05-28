"""CLI entrypoint that generates and persists the synthetic fraud dataset.

Writes:
    backend/data/raw/train.parquet
    backend/data/raw/test.parquet
    backend/data/reference/reference.parquet

Resolves paths relative to the repository so it can be invoked from the
project root (``python -m backend.scripts.generate_data`` or
``python backend/scripts/generate_data.py``) and from inside containers.
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
from src.data.generator import (  # noqa: E402
    DEFAULT_SEED,
    generate_dataset,
    split_dataset,
)
from src.features.constants import (  # noqa: E402
    DEFAULT_DATASET_SIZE,
    DEFAULT_REFERENCE_ROWS,
    DEFAULT_TEST_SIZE,
)
from src.features.validators import validate_dataset  # noqa: E402

RAW_DIR = _BACKEND_ROOT / "data" / "raw"
REFERENCE_DIR = _BACKEND_ROOT / "data" / "reference"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic fraud dataset")
    parser.add_argument(
        "--rows",
        type=int,
        default=DEFAULT_DATASET_SIZE,
        help=f"Total rows to generate (default: {DEFAULT_DATASET_SIZE})",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=DEFAULT_TEST_SIZE,
        help=f"Fraction held out for test (default: {DEFAULT_TEST_SIZE})",
    )
    parser.add_argument(
        "--reference-rows",
        type=int,
        default=DEFAULT_REFERENCE_ROWS,
        help=f"Rows used as drift reference (default: {DEFAULT_REFERENCE_ROWS})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed (default: {DEFAULT_SEED})",
    )
    return parser.parse_args()


def main() -> int:
    """Generate, validate, split, and persist the synthetic dataset."""
    configure_logging()
    args = _parse_args()

    logger.info("Generating synthetic dataset: rows={} seed={}", args.rows, args.seed)
    df = generate_dataset(n_rows=args.rows, seed=args.seed)
    fraud_rate = float(df["is_fraud"].mean())
    logger.info("Generated {} rows | fraud_rate={:.4f}", len(df), fraud_rate)

    result = validate_dataset(df)
    if not result.ok:
        for issue in result.issues:
            logger.error("validation issue: {}", issue)
        result.raise_if_invalid()
    logger.info("Dataset validation passed")

    train_df, test_df, reference_df = split_dataset(
        df,
        test_size=args.test_size,
        reference_rows=args.reference_rows,
        seed=args.seed,
    )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    train_path = RAW_DIR / "train.parquet"
    test_path = RAW_DIR / "test.parquet"
    reference_path = REFERENCE_DIR / "reference.parquet"

    train_df.to_parquet(train_path, index=False)
    test_df.to_parquet(test_path, index=False)
    reference_df.to_parquet(reference_path, index=False)

    logger.info("Wrote train      ({} rows) -> {}", len(train_df), train_path)
    logger.info("Wrote test       ({} rows) -> {}", len(test_df), test_path)
    logger.info("Wrote reference  ({} rows) -> {}", len(reference_df), reference_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
