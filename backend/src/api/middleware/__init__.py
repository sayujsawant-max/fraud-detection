"""FastAPI middleware package.

Phase 7 only ships the Prometheus metrics middleware; future phases can
add request-id propagation, structured access logging, etc. here.
"""

from src.api.middleware.metrics import PrometheusMiddleware

__all__ = ["PrometheusMiddleware"]
