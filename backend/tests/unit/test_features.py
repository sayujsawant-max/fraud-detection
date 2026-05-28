"""Unit tests for the sklearn feature preprocessing pipeline."""

from __future__ import annotations

import numpy as np
import pytest

from src.data.generator import generate_dataset
from src.features.constants import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
)
from src.features.pipeline import build_preprocessor, select_features


def test_select_features_returns_only_feature_columns() -> None:
    df = generate_dataset(n_rows=200, seed=1)
    x = select_features(df)
    assert list(x.columns) == FEATURE_COLUMNS
    assert len(x) == len(df)


def test_select_features_raises_on_missing_column() -> None:
    df = generate_dataset(n_rows=200, seed=1).drop(columns=["transaction_amount"])
    with pytest.raises(KeyError):
        select_features(df)


def test_preprocessor_transforms_to_numeric_matrix() -> None:
    df = generate_dataset(n_rows=500, seed=2)
    x = select_features(df)
    pre = build_preprocessor()
    transformed = pre.fit_transform(x)
    assert transformed.shape == (
        500,
        len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES),
    )
    assert np.issubdtype(transformed.dtype, np.number)
    assert not np.isnan(transformed).any()


def test_preprocessor_handles_unseen_categories() -> None:
    df = generate_dataset(n_rows=400, seed=3)
    x = select_features(df)
    pre = build_preprocessor()
    pre.fit(x)

    novel = x.head(5).copy()
    novel.loc[:, "merchant_category"] = "atlantis_bazaar"
    novel.loc[:, "browser_type"] = "lynx-quantum"

    transformed = pre.transform(novel)
    assert transformed.shape == (
        5,
        len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES),
    )
    assert (transformed == -1).any()


def test_preprocessor_imputes_missing_numeric_values() -> None:
    df = generate_dataset(n_rows=300, seed=4)
    x = select_features(df)
    x.loc[x.index[:10], "transaction_amount"] = np.nan
    pre = build_preprocessor()
    transformed = pre.fit_transform(x)
    assert not np.isnan(transformed).any()
