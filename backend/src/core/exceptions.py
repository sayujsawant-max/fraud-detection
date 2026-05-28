"""Domain-specific exception classes used across the FraudShield backend."""


class FraudShieldError(Exception):
    """Base class for all FraudShield application errors."""


class ModelNotLoadedError(FraudShieldError):
    """Raised when a prediction is attempted before a model is loaded."""


class PredictionError(FraudShieldError):
    """Raised when the loaded model fails to score an input."""


class InvalidModelOutputError(FraudShieldError):
    """Raised when the model returns a malformed probability or label."""


class DataValidationError(FraudShieldError):
    """Raised when input data fails schema or range validation."""


class DriftDetectionError(FraudShieldError):
    """Raised when drift detection cannot be computed."""


# Phase 5 — finer-grained drift errors. Kept distinct from
# :class:`DriftDetectionError` so callers can decide between 404 (report
# missing), 422 (bad inputs), and 500 (Evidently/Postgres blew up).
class DriftError(FraudShieldError):
    """Raised when the Evidently drift computation fails."""


class DriftDataError(FraudShieldError):
    """Raised when reference / current data cannot be assembled.

    Examples: reference.parquet missing, prediction_logs JSONB malformed.
    Distinct from :class:`DriftError` so the API can return 422/503 rather
    than a generic 500.
    """


class DriftReportNotFoundError(FraudShieldError):
    """Raised when ``/v1/monitoring/drift-reports/{id}`` finds no row."""


class RetrainingError(FraudShieldError):
    """Raised when the retraining flow fails.

    Includes invalid trigger reasons, MLflow registry errors during
    promotion, and any unhandled exception bubbling out of a Prefect task.
    """


class InvalidAPIKeyError(FraudShieldError):
    """Raised when an admin endpoint is called without a valid API key."""


class DatabaseError(FraudShieldError):
    """Raised when the database is unreachable or misbehaving.

    Distinguished from generic prediction failures so the API can surface a
    503 from /ready while still letting /v1/predict succeed when only the
    audit-logging side fails.
    """


class PredictionLogNotFoundError(FraudShieldError):
    """Raised when GET /v1/logs/{log_id} cannot find the requested record."""
