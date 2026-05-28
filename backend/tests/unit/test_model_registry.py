"""Unit tests for ``MlflowRegistryClient`` (Phase 2).

The client is exercised against a ``MagicMock`` MLflow client so the tests
run without a tracking server and without Docker.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from mlflow.exceptions import MlflowException

from scripts.train_with_mlflow import select_champion
from src.models.registry import (
    PRODUCTION_ALIAS,
    STAGE_TAG_KEY,
    MlflowRegistryClient,
)


def _make_client() -> tuple[MlflowRegistryClient, MagicMock]:
    mock = MagicMock()
    registry = MlflowRegistryClient(client=mock)
    return registry, mock


def test_init_requires_uri_when_no_client_given() -> None:
    with pytest.raises(ValueError):
        MlflowRegistryClient()


def test_register_model_creates_registered_model_when_missing() -> None:
    registry, mock = _make_client()
    mock.get_registered_model.side_effect = MlflowException("missing")
    mock.create_model_version.return_value = SimpleNamespace(version="1")

    result = registry.register_model("runs:/abc/model", "fraud-detector")

    mock.create_registered_model.assert_called_once_with("fraud-detector")
    mock.create_model_version.assert_called_once_with(
        name="fraud-detector", source="runs:/abc/model"
    )
    assert result.version == "1"


def test_register_model_reuses_existing_registered_model() -> None:
    registry, mock = _make_client()
    mock.get_registered_model.return_value = SimpleNamespace(name="fraud-detector")
    mock.create_model_version.return_value = SimpleNamespace(version="2")

    registry.register_model("runs:/def/model", "fraud-detector")

    mock.create_registered_model.assert_not_called()
    mock.create_model_version.assert_called_once()


def test_get_latest_model_version_returns_highest_numeric() -> None:
    registry, mock = _make_client()
    mock.search_model_versions.return_value = [
        SimpleNamespace(version="1"),
        SimpleNamespace(version="3"),
        SimpleNamespace(version="2"),
    ]
    latest = registry.get_latest_model_version("fraud-detector")
    assert latest is not None
    assert latest.version == "3"


def test_get_latest_model_version_returns_none_when_no_versions() -> None:
    registry, mock = _make_client()
    mock.search_model_versions.return_value = []
    assert registry.get_latest_model_version("fraud-detector") is None


def test_promote_sets_alias_and_stage_tag() -> None:
    registry, mock = _make_client()
    registry.promote_model_to_production("fraud-detector", 7)

    mock.set_registered_model_alias.assert_called_once_with(
        name="fraud-detector", alias=PRODUCTION_ALIAS, version="7"
    )
    mock.set_model_version_tag.assert_called_once_with(
        name="fraud-detector", version="7", key=STAGE_TAG_KEY, value="Production"
    )


def test_archive_old_versions_tags_others_only() -> None:
    registry, mock = _make_client()
    mock.search_model_versions.return_value = [
        SimpleNamespace(version="1"),
        SimpleNamespace(version="2"),
        SimpleNamespace(version="3"),
    ]
    archived = registry.archive_old_versions("fraud-detector", exclude_version=3)
    assert set(archived) == {"1", "2"}
    call_args_list = mock.set_model_version_tag.call_args_list
    tagged_versions = {call.kwargs["version"] for call in call_args_list}
    assert tagged_versions == {"1", "2"}
    for call in call_args_list:
        assert call.kwargs["key"] == STAGE_TAG_KEY
        assert call.kwargs["value"] == "Archived"


def test_get_production_model_info_resolves_alias() -> None:
    registry, mock = _make_client()
    mock.get_model_version_by_alias.return_value = SimpleNamespace(
        name="fraud-detector",
        version="4",
        run_id="run-xyz",
        source="runs:/run-xyz/model",
        aliases=[PRODUCTION_ALIAS],
        tags={"stage": "Production"},
    )
    info = registry.get_production_model_info("fraud-detector")
    assert info is not None
    assert info.version == "4"
    assert PRODUCTION_ALIAS in info.aliases
    assert info.as_dict()["tags"]["stage"] == "Production"


def test_get_production_model_info_returns_none_when_alias_missing() -> None:
    registry, mock = _make_client()
    mock.get_model_version_by_alias.side_effect = MlflowException("no alias")
    assert registry.get_production_model_info("fraud-detector") is None


def test_select_champion_picks_highest_pr_auc() -> None:
    results = [
        {"model_type": "lr", "pr_auc": 0.25, "run_id": "a"},
        {"model_type": "rf", "pr_auc": 0.31, "run_id": "b"},
        {"model_type": "xgb", "pr_auc": 0.28, "run_id": "c"},
    ]
    champion = select_champion(results)
    assert champion["model_type"] == "rf"
    assert champion["run_id"] == "b"


def test_select_champion_rejects_empty_results() -> None:
    with pytest.raises(ValueError):
        select_champion([])
