"""Unit tests for the synthetic fraud data generator."""

from __future__ import annotations

import pandas as pd

from src.data.generator import generate_dataset, split_dataset
from src.features.constants import ALL_COLUMNS, TARGET_COLUMN


def test_generate_dataset_shape() -> None:
    df = generate_dataset(n_rows=5_000, seed=123)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 5_000
    assert list(df.columns) == ALL_COLUMNS


def test_generate_dataset_fraud_rate_in_range() -> None:
    df = generate_dataset(n_rows=10_000, seed=7)
    fraud_rate = float(df[TARGET_COLUMN].mean())
    assert 0.02 <= fraud_rate <= 0.10, f"fraud_rate={fraud_rate}"


def test_generate_dataset_required_columns_present() -> None:
    df = generate_dataset(n_rows=1_000, seed=1)
    for col in ALL_COLUMNS:
        assert col in df.columns, f"missing column {col}"
    assert df[TARGET_COLUMN].isin({0, 1}).all()
    assert (df["transaction_amount"] > 0).all()


def test_generate_dataset_is_reproducible() -> None:
    df_a = generate_dataset(n_rows=2_000, seed=99)
    df_b = generate_dataset(n_rows=2_000, seed=99)
    pd.testing.assert_frame_equal(df_a, df_b)


def test_split_dataset_partitions_disjointly() -> None:
    df = generate_dataset(n_rows=5_000, seed=11)
    train, test, reference = split_dataset(
        df, test_size=0.2, reference_rows=500, seed=11
    )
    assert len(train) + len(test) == len(df)
    assert len(reference) == 500
    assert list(train.columns) == ALL_COLUMNS
    assert list(test.columns) == ALL_COLUMNS
    assert list(reference.columns) == ALL_COLUMNS
