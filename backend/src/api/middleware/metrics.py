"""HTTP middleware that records FraudShield request metrics.

The default ``prometheus-fastapi-instrumentator`` instruments under its
own metric names (``http_request_duration_seconds`` etc.) and its label
shape is fixed. Phase 7 wants a project-prefixed namespace
(``fraudshield_requests_total`` / ``fraudshield_request_duration_seconds`` /
``fraudshield_requests_in_progress``) with stable, low-cardinality labels.

This middleware does the project-prefixed accounting alongside the
instrumentator. It maps each request to its **route template** rather
than its raw path so we don't leak high-cardinality URLs (UUIDs,
report ids) into the ``endpoint`` label.
"""

from __future__ import annotations

import time

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

from src.core.metrics import (
    REQUEST_DURATION_SECONDS,
    REQUESTS_IN_PROGRESS,
    REQUESTS_TOTAL,
)

# Endpoints we want to omit from the request totals — they're already
# covered by Prometheus' own scrape metadata, and emitting them would
# create a self-referential pulse every scrape interval.
_EXCLUDED_PATHS: frozenset[str] = frozenset({"/metrics", "/health", "/ready"})


def _resolve_endpoint(request: Request) -> str:
    """Return the matched route template, falling back to the raw path.

    The Starlette router walks every route looking for a ``Match.FULL`` so
    we always end up with a low-cardinality template like
    ``/v1/retraining/runs/{run_id}`` instead of the raw UUID.
    """
    router = request.app.router if hasattr(request, "app") else None
    if router is None:
        return request.url.path

    for route in getattr(router, "routes", []):
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return getattr(route, "path", request.url.path)
    return request.url.path


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record ``fraudshield_requests_*`` metrics around every HTTP call."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if path in _EXCLUDED_PATHS:
            return await call_next(request)

        endpoint = _resolve_endpoint(request)
        method = request.method
        in_progress = REQUESTS_IN_PROGRESS.labels(endpoint=endpoint)

        try:
            in_progress.inc()
        except Exception as exc:  # noqa: BLE001 — metrics never break the request path
            logger.warning("REQUESTS_IN_PROGRESS.inc failed: {}", exc)

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            # Bubble — the exception handlers will turn this into a 500.
            raise
        finally:
            duration = time.perf_counter() - start
            try:
                REQUEST_DURATION_SECONDS.labels(endpoint=endpoint).observe(duration)
                REQUESTS_TOTAL.labels(
                    method=method,
                    endpoint=endpoint,
                    http_status=str(status_code),
                ).inc()
                in_progress.dec()
            except Exception as exc:  # noqa: BLE001
                logger.warning("metrics flush failed: {}", exc)
