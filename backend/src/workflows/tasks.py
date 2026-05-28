"""Prefect 3 compatibility wrapper used by every FraudShield flow.

Prefect's API has shifted in subtle ways between 2.x and 3.x: ``Flow.serve``
gained new kwargs, deployments changed shape, and ``flow_run.task`` was
renamed. Centralising the imports here means the rest of the codebase
only needs to know two names — ``@flow`` and ``@task`` — and a single
patch keeps the whole project unbroken if Prefect ships another rename.

When Prefect is not installed (e.g. inside a CI image stripped down to
unit tests) the imports raise ``ImportError`` — but unit tests for the
flows always patch the flow callable via monkeypatching, so this module
is never imported directly in the test paths that mock Prefect.
"""

from __future__ import annotations

from typing import Any

try:
    from prefect import flow as _prefect_flow
    from prefect import task as _prefect_task

    PREFECT_AVAILABLE: bool = True
except ImportError:  # pragma: no cover — exercised only when prefect is absent
    PREFECT_AVAILABLE = False

    def _noop_decorator(*args: Any, **kwargs: Any) -> Any:
        """Fall back to a plain passthrough so flows still import cleanly."""

        def _wrap(func: Any) -> Any:
            return func

        if args and callable(args[0]) and not kwargs:
            return args[0]
        return _wrap

    _prefect_flow = _noop_decorator  # type: ignore[assignment]
    _prefect_task = _noop_decorator  # type: ignore[assignment]


# Public aliases used throughout :mod:`src.workflows`. Keeping the names
# short — ``flow`` and ``task`` — preserves Prefect's documented surface.
flow = _prefect_flow
task = _prefect_task

__all__ = ["PREFECT_AVAILABLE", "flow", "task"]
