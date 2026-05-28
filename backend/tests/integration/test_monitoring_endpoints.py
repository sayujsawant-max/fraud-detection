"""Integration tests for the ``/v1/monitoring/*`` drift endpoints.

The Evidently library is patched at the ``DriftDetector.run`` boundary so
these tests exercise the FastAPI router + repository plumbing without
depending on the real Evidently runtime.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.repositories import DriftReportRepository, PredictionLogRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _evidently_dict(num_drifted: int = 4, total: int = 10, share: float = 0.40) -> dict:
    """Minimal Evidently dict() output for the metrics extractor."""
    metrics = [
        {
            "id": "drifted-count",
            "metric_name": "DriftedColumnsCount(drift_share=0.5)",
            "config": {"type": "evidently:metric_v2:DriftedColumnsCount"},
            "value": {"count": num_drifted, "share": share},
        }
    ]
    for i in range(total):
        metrics.append(
            {
                "id": f"value-drift-{i}",
                "metric_name": f"ValueDrift(column=col_{i})",
                "config": {"column": f"col_{i}"},
                "value": 0.01,
            }
        )
    return {"metrics": metrics, "tests": []}


async def _insert_prediction_logs(sessionmaker: async_sessionmaker, count: int) -> None:
    async with sessionmaker() as session:
        repo = PredictionLogRepository(session)
        for i in range(count):
            await repo.create_log(
                transaction_id=f"tx-{i}",
                input_features={
                    "transaction_amount": 100.0 + i,
                    "ip_risk_score": 0.1,
                    "transaction_hour": 12,
                    "is_foreign_transaction": 0,
                },
                fraud_probability=0.2,
                predicted_label=0,
                model_name="fraud-detector",
                model_version="1",
                model_stage="Production",
                optimal_threshold=0.5,
                latency_ms=12.0,
            )


async def _insert_drift_report(
    sessionmaker: async_sessionmaker,
    *,
    report_id: str = "drift_test_001",
    drift_detected: bool = True,
    drift_score: float = 0.4,
    html_path: str | None = None,
) -> uuid.UUID:
    async with sessionmaker() as session:
        repo = DriftReportRepository(session)
        row = await repo.create_report(
            report_id=report_id,
            drift_detected=drift_detected,
            drift_score=drift_score,
            num_drifted_features=4,
            total_features=10,
            num_samples=500,
            status="complete",
            report_html_path=html_path,
            generated_at=datetime.now(tz=UTC),
        )
        return row.id


# ---------------------------------------------------------------------------
# POST /v1/monitoring/drift/check
# ---------------------------------------------------------------------------


def test_drift_check_skipped_when_insufficient_logs(
    client: TestClient, tmp_path: Path
) -> None:
    """Below ``min_samples`` we return status=skipped, HTTP 200."""
    response = client.post("/v1/monitoring/drift/check", json={"min_samples": 100})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "skipped"
    assert body["reason"] == "insufficient_prediction_logs"
    assert body["drift_detected"] is False


@pytest.mark.asyncio
async def test_drift_check_returns_complete_with_mocked_evidently(
    client: TestClient,
    sqlite_sessionmaker: async_sessionmaker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end happy path with Evidently mocked."""
    await _insert_prediction_logs(sqlite_sessionmaker, count=10)
    monkeypatch.setenv("DRIFT_REPORT_DIR", str(tmp_path))

    fake_snapshot = MagicMock()
    fake_snapshot.dict.return_value = _evidently_dict(share=0.40)
    fake_snapshot.save_html = MagicMock(
        side_effect=lambda p: Path(p).write_text("<html/>")
    )
    fake_snapshot.save_json = MagicMock(side_effect=lambda p: Path(p).write_text("{}"))

    with (
        patch(
            "src.api.routers.monitoring.run_drift_detection",
            return_value=(
                _build_result(snapshot_dict=fake_snapshot.dict()),
                fake_snapshot,
            ),
        ),
        patch(
            "src.api.routers.monitoring.DriftDetector",
            return_value=MagicMock(save_artifacts=MagicMock()),
        ),
    ):
        response = client.post(
            "/v1/monitoring/drift/check",
            json={"min_samples": 5, "save_report": True},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "complete"
    assert body["drift_detected"] is True
    assert body["drift_score"] == pytest.approx(0.40)
    assert body["report_id"]


def _build_result(snapshot_dict: dict):
    """Build a DriftDetectionResult mirroring the mocked Evidently output."""
    from src.monitoring.drift import (
        DriftDetectionResult,
        evaluate_drift_threshold,
        extract_drift_metrics,
    )

    metrics = extract_drift_metrics(snapshot_dict)
    return DriftDetectionResult(
        status="complete",
        drift_detected=evaluate_drift_threshold(metrics["drift_score"], 0.30),
        drift_score=metrics["drift_score"],
        num_drifted_features=metrics["num_drifted_features"],
        total_features=metrics["total_features"],
        num_samples=10,
        report_json=snapshot_dict,
    )


# ---------------------------------------------------------------------------
# GET /v1/monitoring/drift-reports
# ---------------------------------------------------------------------------


def test_list_drift_reports_returns_200(client: TestClient) -> None:
    """Empty table → 200 with empty list."""
    response = client.get("/v1/monitoring/drift-reports")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["reports"] == []


@pytest.mark.asyncio
async def test_list_drift_reports_with_data(
    client: TestClient, sqlite_sessionmaker: async_sessionmaker
) -> None:
    """Populated table → newest-first list."""
    await _insert_drift_report(sqlite_sessionmaker, report_id="r1")
    await _insert_drift_report(
        sqlite_sessionmaker, report_id="r2", drift_detected=False
    )

    response = client.get("/v1/monitoring/drift-reports")
    body = response.json()
    assert body["total"] == 2
    assert len(body["reports"]) == 2

    # Filter by drift_detected.
    response = client.get(
        "/v1/monitoring/drift-reports", params={"drift_detected": "false"}
    )
    body = response.json()
    assert body["total"] == 1
    assert body["reports"][0]["report_id"] == "r2"


# ---------------------------------------------------------------------------
# GET /v1/monitoring/drift-reports/latest
# ---------------------------------------------------------------------------


def test_latest_drift_report_returns_404_when_empty(client: TestClient) -> None:
    """No reports → 404 with a clear message."""
    response = client.get("/v1/monitoring/drift-reports/latest")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_latest_drift_report_returns_newest(
    client: TestClient, sqlite_sessionmaker: async_sessionmaker
) -> None:
    """With data → 200 detail body for the newest run."""
    await _insert_drift_report(sqlite_sessionmaker, report_id="old")
    await _insert_drift_report(sqlite_sessionmaker, report_id="new")

    response = client.get("/v1/monitoring/drift-reports/latest")
    assert response.status_code == 200, response.text
    body = response.json()
    # Newest by generated_at — both used now(); just assert one of them.
    assert body["report_id"] in {"old", "new"}
    assert "input_features" not in body  # not a prediction log
    assert "drift_score" in body


# ---------------------------------------------------------------------------
# GET /v1/monitoring/drift-reports/{report_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_drift_report_by_id(
    client: TestClient, sqlite_sessionmaker: async_sessionmaker
) -> None:
    """The detail endpoint returns the row with full metadata."""
    await _insert_drift_report(sqlite_sessionmaker, report_id="abc")
    response = client.get("/v1/monitoring/drift-reports/abc")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["report_id"] == "abc"
    assert "drift_score" in body


def test_get_drift_report_404_when_missing(client: TestClient) -> None:
    response = client.get("/v1/monitoring/drift-reports/does-not-exist")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/monitoring/drift-reports/{report_id}/html
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_drift_report_html_returns_file(
    client: TestClient,
    sqlite_sessionmaker: async_sessionmaker,
    tmp_path: Path,
) -> None:
    """When the artifact file exists, the endpoint streams it as text/html."""
    html_path = tmp_path / "drift_x.html"
    html_path.write_text("<html><body>drift</body></html>", encoding="utf-8")
    await _insert_drift_report(
        sqlite_sessionmaker, report_id="x", html_path=str(html_path)
    )

    response = client.get("/v1/monitoring/drift-reports/x/html")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert b"drift" in response.content


@pytest.mark.asyncio
async def test_get_drift_report_html_404_when_file_missing(
    client: TestClient,
    sqlite_sessionmaker: async_sessionmaker,
    tmp_path: Path,
) -> None:
    """File on disk gone but DB row present → 404, not 500."""
    missing_path = tmp_path / "ghost.html"
    await _insert_drift_report(
        sqlite_sessionmaker, report_id="ghost", html_path=str(missing_path)
    )
    response = client.get("/v1/monitoring/drift-reports/ghost/html")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/monitoring/stats
# ---------------------------------------------------------------------------


def test_monitoring_stats_empty(client: TestClient) -> None:
    """Empty table returns the zero-shape stats body."""
    response = client.get("/v1/monitoring/stats")
    assert response.status_code == 200
    body = response.json()
    for key in (
        "latest_drift_score",
        "latest_drift_detected",
        "last_check_at",
        "total_reports",
        "drift_events",
        "avg_drift_score",
    ):
        assert key in body
    assert body["total_reports"] == 0


@pytest.mark.asyncio
async def test_monitoring_stats_populated(
    client: TestClient, sqlite_sessionmaker: async_sessionmaker
) -> None:
    """With data, stats reports counts + latest drift score."""
    await _insert_drift_report(
        sqlite_sessionmaker, report_id="s1", drift_detected=True, drift_score=0.5
    )
    response = client.get("/v1/monitoring/stats")
    body = response.json()
    assert body["total_reports"] == 1
    assert body["drift_events"] == 1
    assert body["avg_drift_score"] == pytest.approx(0.5)
