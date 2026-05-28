"""ORM model package.

Importing this module is what registers the concrete tables on
``Base.metadata``. Alembic's ``env.py`` imports this package so
autogenerate sees every model without having to enumerate them by hand.
"""

from src.db.models.drift_report import DriftReport
from src.db.models.prediction import PredictionLog
from src.db.models.retraining_run import RetrainingRun

__all__ = ["DriftReport", "PredictionLog", "RetrainingRun"]
