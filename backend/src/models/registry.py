"""MLflow model-registry client for the FraudShield ``fraud-detector`` model.

MLflow 3.x removes the legacy ``Stage`` taxonomy (``None``/``Staging``/
``Production``/``Archived``) and steers users toward *aliases* — short
mutable pointers to a specific model version. We use the alias
``production`` as the canonical pointer for the live model and mirror the
old "stage" semantics via a ``stage`` tag on each model version so the
information is still discoverable through the UI and the API.

The class is built around a small, mockable surface so the unit tests can
inject a ``MagicMock`` instead of standing up a real tracking server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger
from mlflow import MlflowException
from mlflow.entities.model_registry import ModelVersion
from mlflow.tracking import MlflowClient

PRODUCTION_ALIAS: str = "production"
CHAMPION_ALIAS: str = "champion"
STAGE_TAG_KEY: str = "stage"


@dataclass(frozen=True)
class ProductionModelInfo:
    """Snapshot of the model version currently aliased ``production``."""

    name: str
    version: str
    run_id: str | None
    source: str | None
    aliases: list[str]
    tags: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the snapshot."""
        return {
            "name": self.name,
            "version": self.version,
            "run_id": self.run_id,
            "source": self.source,
            "aliases": list(self.aliases),
            "tags": dict(self.tags),
        }


class MlflowRegistryClient:
    """Thin wrapper over :class:`mlflow.tracking.MlflowClient`.

    Args:
        tracking_uri: MLflow tracking server URI. Required when ``client`` is
            not supplied; ignored otherwise.
        client: Optional pre-built ``MlflowClient`` (used by tests).
    """

    def __init__(
        self,
        tracking_uri: str | None = None,
        client: MlflowClient | None = None,
    ) -> None:
        if client is None:
            if not tracking_uri:
                raise ValueError("tracking_uri is required when client is not provided")
            client = MlflowClient(tracking_uri=tracking_uri)
        self._client = client

    @property
    def client(self) -> MlflowClient:
        """Expose the underlying MLflow client (mostly for tests)."""
        return self._client

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def ensure_registered_model(self, model_name: str) -> None:
        """Create the registered model entry if it does not exist yet."""
        try:
            self._client.get_registered_model(model_name)
        except MlflowException:
            logger.info("creating registered model {!r}", model_name)
            self._client.create_registered_model(model_name)

    def register_model(self, model_uri: str, model_name: str) -> ModelVersion:
        """Register ``model_uri`` as a new version of ``model_name``."""
        self.ensure_registered_model(model_name)
        logger.info("registering model {!r} from uri={}", model_name, model_uri)
        version = self._client.create_model_version(
            name=model_name,
            source=model_uri,
        )
        logger.info("registered {!r} as version {}", model_name, version.version)
        return version

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_latest_model_version(self, model_name: str) -> ModelVersion | None:
        """Return the most-recently-created version of ``model_name``, if any."""
        try:
            versions = self._client.search_model_versions(f"name='{model_name}'")
        except MlflowException as exc:
            logger.warning("search_model_versions failed: {}", exc)
            return None
        if not versions:
            return None
        return max(versions, key=lambda v: int(v.version))

    def get_production_model_info(self, model_name: str) -> ProductionModelInfo | None:
        """Resolve the version currently pointed to by the production alias."""
        try:
            mv = self._client.get_model_version_by_alias(model_name, PRODUCTION_ALIAS)
        except MlflowException:
            return None
        return ProductionModelInfo(
            name=mv.name,
            version=str(mv.version),
            run_id=getattr(mv, "run_id", None),
            source=getattr(mv, "source", None),
            aliases=list(getattr(mv, "aliases", []) or []),
            tags=dict(getattr(mv, "tags", {}) or {}),
        )

    # ------------------------------------------------------------------
    # Promotion + archival
    # ------------------------------------------------------------------

    def promote_model_to_production(self, model_name: str, version: str | int) -> None:
        """Point the ``production`` alias at ``version`` and tag it."""
        version_str = str(version)
        logger.info(
            "promoting {!r} version {} to alias {!r}",
            model_name,
            version_str,
            PRODUCTION_ALIAS,
        )
        self._client.set_registered_model_alias(
            name=model_name,
            alias=PRODUCTION_ALIAS,
            version=version_str,
        )
        self._client.set_model_version_tag(
            name=model_name,
            version=version_str,
            key=STAGE_TAG_KEY,
            value="Production",
        )

    def archive_old_versions(
        self, model_name: str, exclude_version: str | int
    ) -> list[str]:
        """Tag every other version as ``Archived`` and return their numbers."""
        keep = str(exclude_version)
        archived: list[str] = []
        try:
            versions = self._client.search_model_versions(f"name='{model_name}'")
        except MlflowException as exc:
            logger.warning("search_model_versions failed during archival: {}", exc)
            return archived

        for mv in versions:
            if str(mv.version) == keep:
                continue
            self._client.set_model_version_tag(
                name=model_name,
                version=str(mv.version),
                key=STAGE_TAG_KEY,
                value="Archived",
            )
            archived.append(str(mv.version))
        if archived:
            logger.info("archived {!r} versions: {}", model_name, archived)
        return archived
