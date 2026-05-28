"""Unit tests for :func:`verify_api_key`.

The dependency is a plain function — no FastAPI machinery needed — so
the tests call it directly and assert on the raised ``HTTPException``.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.api.dependencies import verify_api_key
from src.core.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    """Force a fresh ``Settings`` so per-test ``API_KEY`` overrides apply.

    ``get_settings`` is ``lru_cache``-decorated, so we clear it here to
    keep tests from leaking state into each other.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_missing_api_key_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """No header → 403 Forbidden."""
    monkeypatch.setenv("API_KEY", "expected-secret")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        verify_api_key(x_api_key=None)
    assert exc.value.status_code == 403


def test_empty_api_key_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty header value → 403 Forbidden."""
    monkeypatch.setenv("API_KEY", "expected-secret")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        verify_api_key(x_api_key="")
    assert exc.value.status_code == 403


def test_wrong_api_key_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mismatched header value → 403 Forbidden."""
    monkeypatch.setenv("API_KEY", "expected-secret")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        verify_api_key(x_api_key="wrong-key")
    assert exc.value.status_code == 403


def test_correct_api_key_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Matching header → returns the value, no exception."""
    monkeypatch.setenv("API_KEY", "expected-secret")
    get_settings.cache_clear()
    assert verify_api_key(x_api_key="expected-secret") == "expected-secret"


def test_unconfigured_api_key_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings.API_KEY = '' → 503, not 403 (operator misconfiguration)."""
    monkeypatch.setenv("API_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        verify_api_key(x_api_key="anything")
    assert exc.value.status_code == 503
