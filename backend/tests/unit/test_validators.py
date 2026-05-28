"""Unit tests for the dataset validators."""

from __future__ import annotations

import numpy as np
import pytest

from src.data.generator import generate_dataset
from src.features.constants import TARGET_COLUMN
from src.features.validators import (
    DatasetValidationError,
    validate_dataset,
)


def test_validate_dataset_passes_on_valid_data() -> None:
    df = generate_dataset(n_rows=3_000, seed=42)
    result = validate_dataset(df)
    assert result.ok, result.issues


def test_validate_dataset_fails_on_missing_column() -> None:
    df = generate_dataset(n_rows=500, seed=42).drop(columns=["transaction_amount"])
    result = validate_dataset(df)
    assert not result.ok
    assert any("missing required columns" in issue for issue in result.issues)


def test_validate_dataset_fails_on_invalid_target_values() -> None:
    df = generate_dataset(n_rows=500, seed=42)
    df.loc[df.index[0], TARGET_COLUMN] = 7
    result = validate_dataset(df)
    assert not result.ok
    assert any(TARGET_COLUMN in issue and "0/1" in issue for issue in result.issues)


def test_validate_dataset_fails_on_out_of_range_amount() -> None:
    df = generate_dataset(n_rows=500, seed=42)
    df.loc[df.index[0], "transaction_amount"] = -1.0
    result = validate_dataset(df)
    assert not result.ok
    assert any("transaction_amount" in issue for issue in result.issues)


def test_validate_dataset_fails_on_excess_missingness() -> None:
    df = generate_dataset(n_rows=1_000, seed=42)
    # 10% missing in ip_risk_score → above the 5% threshold
    mask = np.zeros(len(df), dtype=bool)
    mask[: int(0.10 * len(df))] = True
    df.loc[mask, "ip_risk_score"] = np.nan
    result = validate_dataset(df)
    assert not result.ok
    assert any("ip_risk_score" in issue for issue in result.issues)


def test_raise_if_invalid_raises() -> None:
    df = generate_dataset(n_rows=500, seed=42).drop(columns=["user_age"])
    result = validate_dataset(df)
    with pytest.raises(DatasetValidationError):
        result.raise_if_invalid()
