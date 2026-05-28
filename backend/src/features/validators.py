"""Dataset validators for the FraudShield synthetic fraud dataset.

Validators enforce contract invariants on the parquet files produced by the
generator before they are consumed by training or drift detection. They
raise ``DatasetValidationError`` with a structured list of issues so callers
can fail fast in CI and in Prefect flows.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.features.constants import (
    ALL_COLUMNS,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
)

MAX_MISSING_RATE: float = 0.05
MIN_FRAUD_RATE: float = 0.01
MAX_FRAUD_RATE: float = 0.20


class DatasetValidationError(ValueError):
    """Raised when a dataset fails one or more contract checks."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        message = "Dataset failed validation:\n  - " + "\n  - ".join(issues)
        super().__init__(message)


@dataclass
class ValidationResult:
    """Outcome of running the validation suite on a dataframe."""

    ok: bool
    issues: list[str] = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        """Raise ``DatasetValidationError`` if validation failed."""
        if not self.ok:
            raise DatasetValidationError(self.issues)


def _check_columns(df: pd.DataFrame) -> list[str]:
    issues: list[str] = []
    expected = set(ALL_COLUMNS)
    actual = set(df.columns)

    missing = expected - actual
    if missing:
        issues.append(f"missing required columns: {sorted(missing)}")

    unexpected = actual - expected
    if unexpected:
        issues.append(f"unexpected columns present: {sorted(unexpected)}")

    return issues


def _check_ranges(df: pd.DataFrame) -> list[str]:
    issues: list[str] = []

    if "transaction_amount" in df.columns and (df["transaction_amount"] <= 0).any():
        issues.append("transaction_amount must be > 0 for every row")

    if "user_age" in df.columns:
        ages = df["user_age"]
        if ((ages < 18) | (ages > 100)).any():
            issues.append("user_age must be within [18, 100]")

    for col in ("credit_utilization", "ip_risk_score"):
        if col in df.columns:
            values = df[col]
            if ((values < 0) | (values > 1)).any():
                issues.append(f"{col} must be within [0, 1]")

    if TARGET_COLUMN in df.columns:
        unique = set(pd.unique(df[TARGET_COLUMN]).tolist())
        if not unique.issubset({0, 1}):
            issues.append(
                f"{TARGET_COLUMN} must contain only 0/1 values, got {sorted(unique)}"
            )

    return issues


def _check_fraud_rate(df: pd.DataFrame) -> list[str]:
    if TARGET_COLUMN not in df.columns:
        return []
    rate = float(df[TARGET_COLUMN].mean())
    if not (MIN_FRAUD_RATE <= rate <= MAX_FRAUD_RATE):
        return [
            f"fraud rate {rate:.4f} outside acceptable range "
            f"[{MIN_FRAUD_RATE}, {MAX_FRAUD_RATE}]"
        ]
    return []


def _check_missingness(df: pd.DataFrame) -> list[str]:
    issues: list[str] = []
    feature_cols = [
        c for c in NUMERIC_FEATURES + CATEGORICAL_FEATURES if c in df.columns
    ]
    if not feature_cols:
        return issues
    missing_rates = df[feature_cols].isna().mean()
    breached = missing_rates[missing_rates > MAX_MISSING_RATE]
    for col, rate in breached.items():
        issues.append(
            f"column {col!r} has {rate:.2%} missing (> {MAX_MISSING_RATE:.0%})"
        )
    return issues


def validate_dataset(df: pd.DataFrame) -> ValidationResult:
    """Run all dataset checks and return a structured result."""
    issues: list[str] = []
    issues.extend(_check_columns(df))
    issues.extend(_check_ranges(df))
    issues.extend(_check_fraud_rate(df))
    issues.extend(_check_missingness(df))
    return ValidationResult(ok=not issues, issues=issues)
