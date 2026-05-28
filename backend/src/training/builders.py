"""Factory functions that build the baseline sklearn pipelines.

Centralising the pipeline definitions here lets the Phase 1 ``train.py``
script and the Phase 2 MLflow-tracked trainer share the exact same model
construction code, eliminating drift between the two entry points.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from src.features.pipeline import build_preprocessor
from src.features.validators import validate_dataset

RANDOM_STATE: int = 42


@dataclass(frozen=True)
class BuiltModel:
    """A named sklearn pipeline plus the hyperparameters used to build it."""

    name: str
    pipeline: Pipeline
    params: dict[str, Any]


def build_logistic_regression() -> BuiltModel:
    """Return the baseline logistic regression pipeline."""
    params: dict[str, Any] = {
        "model_type": "logistic_regression",
        "max_iter": 2_000,
        "class_weight_strategy": "balanced",
        "random_state": RANDOM_STATE,
    }
    pipeline = Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=params["max_iter"],
                    class_weight="balanced",
                    n_jobs=None,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )
    return BuiltModel(name="logistic_regression", pipeline=pipeline, params=params)


def build_random_forest() -> BuiltModel:
    """Return the baseline random forest pipeline."""
    params: dict[str, Any] = {
        "model_type": "random_forest",
        "n_estimators": 200,
        "max_depth": 12,
        "min_samples_leaf": 20,
        "class_weight_strategy": "balanced",
        "random_state": RANDOM_STATE,
    }
    pipeline = Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=params["n_estimators"],
                    max_depth=params["max_depth"],
                    min_samples_leaf=params["min_samples_leaf"],
                    class_weight="balanced",
                    n_jobs=-1,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )
    return BuiltModel(name="random_forest", pipeline=pipeline, params=params)


def build_xgboost(scale_pos_weight: float) -> BuiltModel | None:
    """Return the baseline XGBoost pipeline if xgboost is importable."""
    try:
        from xgboost import XGBClassifier
    except ImportError:
        logger.warning("xgboost is not installed — skipping XGBoost baseline")
        return None

    params: dict[str, Any] = {
        "model_type": "xgboost",
        "n_estimators": 400,
        "max_depth": 6,
        "learning_rate": 0.08,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "scale_pos_weight": round(scale_pos_weight, 4),
        "class_weight_strategy": "scale_pos_weight",
        "tree_method": "hist",
        "random_state": RANDOM_STATE,
    }
    pipeline = Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            (
                "classifier",
                XGBClassifier(
                    n_estimators=params["n_estimators"],
                    max_depth=params["max_depth"],
                    learning_rate=params["learning_rate"],
                    subsample=params["subsample"],
                    colsample_bytree=params["colsample_bytree"],
                    eval_metric="aucpr",
                    scale_pos_weight=scale_pos_weight,
                    tree_method=params["tree_method"],
                    random_state=RANDOM_STATE,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    return BuiltModel(name="xgboost", pipeline=pipeline, params=params)


def load_split(path: Path) -> pd.DataFrame:
    """Load a parquet split from disk and validate it."""
    if not path.exists():
        raise FileNotFoundError(
            f"missing dataset at {path}; run "
            "`python backend/scripts/generate_data.py` first"
        )
    df = pd.read_parquet(path)
    validate_dataset(df).raise_if_invalid()
    return df
