"""Shared pytest fixtures for the FraudShield backend test suite.

Phase 0 fixtures are deliberately minimal — they provide a TestClient bound
to the FastAPI app without requiring Docker, PostgreSQL, MLflow, or trained
models. Database and model fixtures are added in Phase 3.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """Yield a FastAPI TestClient for the application."""
    with TestClient(app) as test_client:
        yield test_client
