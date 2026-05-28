"""Synthetic fraud transaction generator.

Produces a Pandas DataFrame of synthetic credit-card transactions whose
``is_fraud`` label is driven by a logistic model over realistic risk factors
(late-night activity, foreign / high-risk-country transactions, velocity,
account age, distance from home, IP risk, prior fraud history, and unusual
amounts). The intercept of that logistic model is tuned to target an
overall fraud rate of roughly 4–5%.

The generator is deterministic for a given ``seed`` so that tests can rely
on stable shapes and label distributions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.constants import (
    ALL_COLUMNS,
    BROWSER_TYPES,
    CARD_TYPES,
    DEFAULT_DATASET_SIZE,
    DEVICE_TYPES,
    MERCHANT_CATEGORIES,
    TRANSACTION_TYPES,
)

DEFAULT_SEED: int = 42


def _sample_categorical(
    rng: np.random.Generator,
    choices: list[str],
    size: int,
    probs: list[float] | None = None,
) -> np.ndarray:
    return rng.choice(choices, size=size, p=probs)


def _fraud_logit(df: pd.DataFrame) -> np.ndarray:
    """Compute the per-row logit driving the fraud probability."""
    intercept = -4.75
    logit = (
        intercept
        + 1.40 * df["is_late_night"].to_numpy()
        + 1.80 * df["is_foreign_transaction"].to_numpy()
        + 2.20 * df["is_high_risk_country"].to_numpy()
        + 0.95 * df["is_high_velocity"].to_numpy()
        + 1.10 * df["is_new_account"].to_numpy()
        + 0.55 * np.clip(df["amount_z_score"].to_numpy(), -1.0, 6.0)
        + 0.0009 * np.clip(df["distance_from_home_km"].to_numpy(), 0.0, 8_000.0)
        + 2.40 * df["previous_fraud_flag"].to_numpy()
        + 2.10 * df["ip_risk_score"].to_numpy()
        + 0.60 * (df["amount_to_avg_ratio"].to_numpy() > 3.0).astype(float)
    )
    return logit


def generate_dataset(
    n_rows: int = DEFAULT_DATASET_SIZE,
    seed: int = DEFAULT_SEED,
) -> pd.DataFrame:
    """Generate a synthetic fraud detection dataset.

    Args:
        n_rows: Total number of transactions to generate.
        seed: NumPy seed for reproducibility.

    Returns:
        Dataframe with the schema declared in :mod:`src.features.constants`.
    """
    if n_rows <= 0:
        raise ValueError(f"n_rows must be positive, got {n_rows}")

    rng = np.random.default_rng(seed)

    user_age = rng.integers(18, 80, size=n_rows)
    account_age_days = rng.integers(1, 3_650, size=n_rows)
    credit_limit = np.round(rng.uniform(500.0, 50_000.0, size=n_rows), 2)
    credit_utilization = np.clip(rng.beta(2.0, 5.0, size=n_rows), 0.0, 1.0)
    previous_fraud_flag = (rng.random(n_rows) < 0.03).astype(int)

    base_amount = rng.lognormal(mean=3.4, sigma=1.05, size=n_rows)
    amount_spikes = (rng.random(n_rows) < 0.02).astype(float)
    transaction_amount = np.round(
        base_amount * (1.0 + amount_spikes * rng.uniform(5.0, 20.0, n_rows)), 2
    )
    transaction_amount = np.clip(transaction_amount, 0.5, 25_000.0)

    transaction_hour = rng.integers(0, 24, size=n_rows)
    transaction_day_of_week = rng.integers(0, 7, size=n_rows)
    is_weekend = (transaction_day_of_week >= 5).astype(int)
    is_late_night = ((transaction_hour < 5) | (transaction_hour >= 23)).astype(int)

    transaction_count_24h = rng.poisson(lam=2.5, size=n_rows)
    transaction_count_7d = transaction_count_24h + rng.poisson(lam=10.0, size=n_rows)
    avg_transaction_amount_30d = np.round(
        rng.lognormal(mean=3.3, sigma=0.7, size=n_rows), 2
    )
    avg_transaction_amount_30d = np.clip(avg_transaction_amount_30d, 1.0, 5_000.0)
    amount_to_avg_ratio = np.round(transaction_amount / avg_transaction_amount_30d, 4)

    unique_merchants_7d = np.minimum(
        transaction_count_7d, rng.integers(1, 15, size=n_rows)
    )
    is_first_transaction_merchant = (rng.random(n_rows) < 0.18).astype(int)

    distance_from_home_km = np.round(rng.exponential(scale=25.0, size=n_rows), 2)
    is_foreign_transaction = (rng.random(n_rows) < 0.04).astype(int)
    is_high_risk_country = (
        is_foreign_transaction & (rng.random(n_rows) < 0.20)
    ).astype(int)

    ip_risk_score = np.clip(rng.beta(1.5, 8.0, size=n_rows), 0.0, 1.0)

    merchant_category = _sample_categorical(rng, MERCHANT_CATEGORIES, n_rows)
    transaction_type = _sample_categorical(
        rng,
        TRANSACTION_TYPES,
        n_rows,
        probs=[0.60, 0.12, 0.13, 0.05, 0.10],
    )
    card_type = _sample_categorical(
        rng, CARD_TYPES, n_rows, probs=[0.50, 0.30, 0.12, 0.08]
    )
    device_type = _sample_categorical(
        rng, DEVICE_TYPES, n_rows, probs=[0.55, 0.30, 0.10, 0.05]
    )
    browser_type = _sample_categorical(
        rng, BROWSER_TYPES, n_rows, probs=[0.45, 0.20, 0.10, 0.10, 0.05, 0.10]
    )

    log_amount = np.round(np.log1p(transaction_amount), 4)
    is_high_velocity = (transaction_count_24h >= 6).astype(int)
    is_new_account = (account_age_days < 30).astype(int)
    amount_mean = float(np.mean(transaction_amount))
    amount_std = float(np.std(transaction_amount)) or 1.0
    amount_z_score = np.round((transaction_amount - amount_mean) / amount_std, 4)

    df = pd.DataFrame(
        {
            "transaction_amount": transaction_amount,
            "transaction_hour": transaction_hour,
            "transaction_day_of_week": transaction_day_of_week,
            "is_weekend": is_weekend,
            "merchant_category": merchant_category,
            "transaction_type": transaction_type,
            "card_type": card_type,
            "transaction_count_24h": transaction_count_24h,
            "transaction_count_7d": transaction_count_7d,
            "avg_transaction_amount_30d": avg_transaction_amount_30d,
            "amount_to_avg_ratio": amount_to_avg_ratio,
            "unique_merchants_7d": unique_merchants_7d,
            "is_first_transaction_merchant": is_first_transaction_merchant,
            "distance_from_home_km": distance_from_home_km,
            "is_foreign_transaction": is_foreign_transaction,
            "is_high_risk_country": is_high_risk_country,
            "device_type": device_type,
            "browser_type": browser_type,
            "ip_risk_score": ip_risk_score,
            "account_age_days": account_age_days,
            "user_age": user_age,
            "credit_limit": credit_limit,
            "credit_utilization": credit_utilization,
            "previous_fraud_flag": previous_fraud_flag,
            "log_amount": log_amount,
            "is_high_velocity": is_high_velocity,
            "is_new_account": is_new_account,
            "is_late_night": is_late_night,
            "amount_z_score": amount_z_score,
        }
    )

    logits = _fraud_logit(df)
    fraud_prob = 1.0 / (1.0 + np.exp(-logits))
    is_fraud = (rng.random(n_rows) < fraud_prob).astype(int)
    df["is_fraud"] = is_fraud

    return df.loc[:, ALL_COLUMNS]


def split_dataset(
    df: pd.DataFrame,
    test_size: float,
    reference_rows: int,
    seed: int = DEFAULT_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Shuffle and split the dataset into train / test / reference frames.

    The reference frame is the first ``reference_rows`` of the (shuffled)
    training set and is used downstream by Evidently as the drift baseline.
    """
    if not 0.0 < test_size < 1.0:
        raise ValueError(f"test_size must be in (0, 1), got {test_size}")
    if reference_rows <= 0:
        raise ValueError(f"reference_rows must be positive, got {reference_rows}")

    shuffled = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    n_test = int(round(len(shuffled) * test_size))
    test_df = shuffled.iloc[:n_test].reset_index(drop=True)
    train_df = shuffled.iloc[n_test:].reset_index(drop=True)

    ref_n = min(reference_rows, len(train_df))
    reference_df = train_df.iloc[:ref_n].reset_index(drop=True)

    return train_df, test_df, reference_df
