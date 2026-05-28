"""Domain-specific exception classes used across the FraudShield backend."""


class FraudShieldError(Exception):
    """Base class for all FraudShield application errors."""


class ModelNotLoadedError(FraudShieldError):
    """Raised when a prediction is attempted before a model is loaded."""


class DataValidationError(FraudShieldError):
    """Raised when input data fails schema or range validation."""


class DriftDetectionError(FraudShieldError):
    """Raised when drift detection cannot be computed."""


class RetrainingError(FraudShieldError):
    """Raised when the retraining flow fails."""
