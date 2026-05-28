"""Repository layer — keeps SQL out of routers and tests easier to write.

Each repository takes an :class:`AsyncSession` in its constructor so the
caller controls the transaction scope. Routers obtain a session via the
``get_db_session`` FastAPI dependency and instantiate the repository on
the spot.
"""

from src.db.repositories.drift_reports import DriftReportRepository
from src.db.repositories.prediction_logs import PredictionLogRepository
from src.db.repositories.retraining_runs import RetrainingRunRepository

__all__ = [
    "DriftReportRepository",
    "PredictionLogRepository",
    "RetrainingRunRepository",
]
