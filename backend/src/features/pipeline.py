"""Reusable scikit-learn preprocessing pipeline for FraudShield features.

The pipeline imputes and scales numeric features, imputes and ordinal-encodes
categorical features, and is designed to be bundled inside the MLflow model
artifact in Phase 2 so the exact same transformations run at serving time.
"""

from __future__ import annotations

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, RobustScaler

from src.features.constants import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
)

UNKNOWN_CATEGORY: str = "unknown"


def build_preprocessor() -> ColumnTransformer:
    """Return a fresh ColumnTransformer for the FraudShield feature set."""
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", RobustScaler()),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="constant", fill_value=UNKNOWN_CATEGORY),
            ),
            (
                "encoder",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                ),
            ),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, NUMERIC_FEATURES),
            ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )


def select_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` restricted to the canonical feature columns."""
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"input dataframe is missing required features: {missing}")
    return df.loc[:, FEATURE_COLUMNS].copy()
