"""Unit tests for :mod:`src.core.metrics`.

These tests poke the metric collectors directly via the
``prometheus_client`` API and never need a running Prometheus server.
They also exercise the ``_get_or_create`` idempotency guard: importing
the metrics module twice must NOT raise
``Duplicated timeseries in CollectorRegistry``.
"""

from __future__ import annotations

import importlib

import pytest
from prometheus_client import generate_latest

import src.core.metrics as metrics_module


def _value(collector, **labels) -> float:
    """Return the current numeric value of a labelled child collector."""
    if labels:
        child = collector.labels(**labels)
    else:
        child = collector
    # Counters expose ``_value.get()``; Gauges do too; Histograms expose
    # ``_sum.get()`` for the sum, plus ``_buckets``.
    if hasattr(child, "_value"):
        return float(child._value.get())  # noqa: SLF001
    return float("nan")


def _sample_value(name: str, **labels) -> float:
    """Look up the sample value of ``name`` (+ matching labels) on the registry.

    Returns ``0.0`` when no matching sample exists yet — Prometheus counts
    unobserved counters as zero, so the assertion math (``before + 1 ==
    after``) works without special-casing the first call.
    """
    from prometheus_client import REGISTRY

    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if sample.name == name and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return float(sample.value)
    return 0.0


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_metrics_module_reimport_does_not_raise() -> None:
    """Re-importing the metrics module must not blow up the registry."""
    importlib.reload(metrics_module)
    # Reloading a second time exercises the get-or-create path again.
    importlib.reload(metrics_module)


def test_get_or_create_returns_same_collector() -> None:
    """Second call with the same name returns the existing collector."""
    from prometheus_client import Counter

    first = metrics_module._get_or_create(  # noqa: SLF001
        Counter,
        "fraudshield_requests_total",
        "Total number of API requests",
        labelnames=("method", "endpoint", "http_status"),
    )
    assert first is metrics_module.REQUESTS_TOTAL


# ---------------------------------------------------------------------------
# Prediction recording
# ---------------------------------------------------------------------------


def test_record_prediction_increments_counter_and_observes_score() -> None:
    """A fraud prediction bumps both the counter and the score histogram."""
    before = _sample_value("fraudshield_predictions_total", label="fraud")
    before_count = _sample_value("fraudshield_prediction_score_count")

    metrics_module.record_prediction(predicted_label=1, fraud_probability=0.82)

    after = _sample_value("fraudshield_predictions_total", label="fraud")
    after_count = _sample_value("fraudshield_prediction_score_count")
    assert after == before + 1
    assert after_count == before_count + 1


def test_record_prediction_legit_uses_legitimate_label() -> None:
    """Predicted 0 → label='legitimate'."""
    before = _sample_value("fraudshield_predictions_total", label="legitimate")
    metrics_module.record_prediction(predicted_label=0, fraud_probability=0.12)
    after = _sample_value("fraudshield_predictions_total", label="legitimate")
    assert after == before + 1


def test_record_batch_observes_batch_size_and_each_score() -> None:
    """``record_batch`` updates the batch-size histogram + per-row counters."""
    before_batch_count = _sample_value("fraudshield_batch_size_count")
    before_count = _sample_value("fraudshield_prediction_score_count")

    metrics_module.record_batch([(1, 0.91), (0, 0.10), (1, 0.55)])

    after_batch_count = _sample_value("fraudshield_batch_size_count")
    after_count = _sample_value("fraudshield_prediction_score_count")
    assert after_batch_count == before_batch_count + 1
    assert after_count == before_count + 3


def test_record_prediction_never_raises_on_bad_input() -> None:
    """Bad ``predicted_label`` must not crash the prediction path."""
    metrics_module.record_prediction(
        predicted_label="not-an-int", fraud_probability="bad"
    )  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Drift recording
# ---------------------------------------------------------------------------


def test_record_drift_check_complete_sets_score_and_bumps_status() -> None:
    """A complete check stamps the gauge and increments the status counter."""
    before = _sample_value("fraudshield_drift_checks_total", status="complete")

    metrics_module.record_drift_check(
        status="complete", drift_score=0.42, drift_detected=False
    )

    after = _sample_value("fraudshield_drift_checks_total", status="complete")
    assert after == before + 1
    assert _sample_value("fraudshield_latest_drift_score") == pytest.approx(0.42)


def test_record_drift_check_detected_bumps_drift_events_counter() -> None:
    """``drift_detected=True`` increments the drift_detected_total counter."""
    before = _sample_value("fraudshield_drift_detected_total")
    metrics_module.record_drift_check(
        status="complete", drift_score=0.55, drift_detected=True
    )
    after = _sample_value("fraudshield_drift_detected_total")
    assert after == before + 1


def test_record_drift_check_skipped_does_not_set_score() -> None:
    """A skipped run with no score keeps the gauge value unchanged."""
    metrics_module.record_drift_check(
        status="complete", drift_score=0.99, drift_detected=False
    )
    pinned = _sample_value("fraudshield_latest_drift_score")
    metrics_module.record_drift_check(
        status="skipped", drift_score=None, drift_detected=False
    )
    assert _sample_value("fraudshield_latest_drift_score") == pytest.approx(pinned)


# ---------------------------------------------------------------------------
# Retraining recording
# ---------------------------------------------------------------------------


def test_record_retraining_run_promoted_updates_all_metrics() -> None:
    """A promoted run increments runs_total + promotions_total + gauges."""
    before_runs = _sample_value(
        "fraudshield_retraining_runs_total", status="promoted", trigger_reason="manual"
    )
    before_promo = _sample_value("fraudshield_model_promotions_total")

    metrics_module.record_retraining_run(
        status="promoted",
        trigger_reason="manual",
        promoted=True,
        challenger_pr_auc=0.91,
        champion_pr_auc=0.88,
    )

    after_runs = _sample_value(
        "fraudshield_retraining_runs_total", status="promoted", trigger_reason="manual"
    )
    after_promo = _sample_value("fraudshield_model_promotions_total")
    assert after_runs == before_runs + 1
    assert after_promo == before_promo + 1
    assert _sample_value("fraudshield_latest_challenger_pr_auc") == pytest.approx(0.91)
    assert _sample_value("fraudshield_latest_champion_pr_auc") == pytest.approx(0.88)


def test_record_retraining_run_rejected_does_not_bump_promotions() -> None:
    """A rejected run leaves promotions_total alone."""
    before = _sample_value("fraudshield_model_promotions_total")
    metrics_module.record_retraining_run(
        status="rejected",
        trigger_reason="scheduled",
        promoted=False,
        challenger_pr_auc=0.70,
        champion_pr_auc=0.85,
    )
    assert _sample_value("fraudshield_model_promotions_total") == before


# ---------------------------------------------------------------------------
# Model-loaded gauges
# ---------------------------------------------------------------------------


def test_record_model_loaded_sets_timestamp_and_info() -> None:
    """``record_model_loaded`` stamps the timestamp + version-info gauge."""
    metrics_module.record_model_loaded(
        model_name="fraud-detector",
        model_version="2",
        model_stage="Production",
        loaded_at_epoch=1_700_000_000.0,
    )
    assert _sample_value("fraudshield_model_load_timestamp") == pytest.approx(
        1_700_000_000.0
    )
    info_val = _sample_value(
        "fraudshield_model_version_info",
        model_name="fraud-detector",
        model_version="2",
        model_stage="Production",
    )
    assert info_val == pytest.approx(1.0)


def test_record_model_loaded_clears_stale_versions() -> None:
    """Loading a new version replaces (not appends) the version-info labels."""
    metrics_module.record_model_loaded(
        model_name="fraud-detector",
        model_version="1",
        model_stage="Production",
        loaded_at_epoch=1_699_000_000.0,
    )
    metrics_module.record_model_loaded(
        model_name="fraud-detector",
        model_version="2",
        model_stage="Production",
        loaded_at_epoch=1_700_000_000.0,
    )
    # The old (version=1) sample should be gone (cleared from the gauge).
    stale = _sample_value(
        "fraudshield_model_version_info",
        model_name="fraud-detector",
        model_version="1",
        model_stage="Production",
    )
    assert stale == 0.0, "stale model_version_info label should be cleared"


# ---------------------------------------------------------------------------
# Exposition format
# ---------------------------------------------------------------------------


def test_generate_latest_includes_fraudshield_metrics() -> None:
    """``generate_latest`` returns the Prometheus exposition payload."""
    # Touch every helper at least once so the rendered output is non-empty.
    metrics_module.record_prediction(1, 0.7)
    metrics_module.record_drift_check(
        status="complete", drift_score=0.2, drift_detected=False
    )

    payload = generate_latest().decode("utf-8")
    assert "fraudshield_predictions_total" in payload
    assert "fraudshield_prediction_score" in payload
    assert "fraudshield_latest_drift_score" in payload
