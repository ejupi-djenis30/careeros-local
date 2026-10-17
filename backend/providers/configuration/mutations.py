"""Focused provider mutations with service-owned atomic transactions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from backend.providers.configuration.models import JobProviderConfiguration
from backend.providers.configuration.native import validate_native_adapter_id
from backend.providers.configuration.schemas import (
    PRESERVE_SECRET,
    REDACTED_SECRET,
    ProviderCapabilitiesConfig,
    ProviderConfigurationCreate,
    ProviderConfigurationInput,
    ProviderConfigurationUpdate,
    ProviderConfigurationView,
    ProviderRequestConfig,
    ProviderStateUpdate,
    secret_header,
)

from .catalog import (
    MAX_PROVIDERS_PER_USER,
    ProviderCatalog,
    ProviderConfigurationError,
    _provider_origin,
    configuration_view,
    materialize_configuration,
)


class ProviderMutations(ProviderCatalog):
    def create(
        self, user_id: int, payload: ProviderConfigurationCreate
    ) -> ProviderConfigurationView:
        self.validate(payload)
        if any(
            value in {PRESERVE_SECRET, REDACTED_SECRET}
            for value in payload.request.headers.values()
        ):
            raise ProviderConfigurationError(
                "invalid_secret_sentinel", "A new provider cannot preserve a missing secret"
            )
        if (
            self.db.query(JobProviderConfiguration)
            .filter(JobProviderConfiguration.user_id == user_id)
            .count()
            >= MAX_PROVIDERS_PER_USER
        ):
            raise ProviderConfigurationError(
                "provider_limit",
                f"At most {MAX_PROVIDERS_PER_USER} providers are allowed",
            )
        row = JobProviderConfiguration(
            user_id=user_id,
            key=payload.key,
            display_name=payload.display_name,
            description=payload.description,
            adapter_kind=payload.adapter_kind,
            native_adapter_id=None,
            source_pack_id=None,
            source_pack_version=None,
            enabled=payload.enabled,
            revision=1,
            request_config=payload.request.model_dump(mode="json"),
            extraction_config=payload.extraction.model_dump(mode="json"),
            capabilities_config=payload.capabilities.model_dump(mode="json"),
        )
        try:
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
        except IntegrityError as exc:
            self.db.rollback()
            raise ProviderConfigurationError(
                "provider_key_conflict", "A provider with this key already exists"
            ) from exc
        return configuration_view(row)

    def update(
        self, user_id: int, configuration_id: str, payload: ProviderConfigurationUpdate
    ) -> ProviderConfigurationView:
        current = self.get_row(user_id, configuration_id)
        if current.adapter_kind == "native":
            raise ProviderConfigurationError(
                "native_provider_read_only",
                "Native providers can only be enabled, disabled or removed",
            )
        merged_headers = dict(payload.request.headers)
        stored_request = ProviderRequestConfig.model_validate(current.request_config)
        stored_headers = stored_request.headers
        origin_changed = _provider_origin(stored_request.base_url) != _provider_origin(
            payload.request.base_url
        )
        if origin_changed and (
            (stored_headers and "headers" not in payload.request.model_fields_set)
            or any(value in {PRESERVE_SECRET, REDACTED_SECRET} for value in merged_headers.values())
        ):
            raise ProviderConfigurationError(
                "secret_origin_changed",
                "Changing provider origin requires explicit replacement or removal of its headers",
            )
        for name, value in merged_headers.items():
            if value not in {PRESERVE_SECRET, REDACTED_SECRET}:
                continue
            if not secret_header(name) or name not in stored_headers:
                raise ProviderConfigurationError(
                    "invalid_secret_sentinel", "The secret-preservation marker is invalid"
                )
            merged_headers[name] = stored_headers[name]
        materialized = ProviderConfigurationInput.model_validate(
            payload.model_dump(exclude={"expected_revision"})
        )
        materialized.request = materialized.request.model_copy(update={"headers": merged_headers})
        self.validate(materialized)
        values: dict[Any, Any] = {
            "key": materialized.key,
            "display_name": materialized.display_name,
            "description": materialized.description,
            "adapter_kind": materialized.adapter_kind,
            "enabled": materialized.enabled,
            "request_config": materialized.request.model_dump(mode="json"),
            "extraction_config": materialized.extraction.model_dump(mode="json"),
            "capabilities_config": materialized.capabilities.model_dump(mode="json"),
            "revision": payload.expected_revision + 1,
            "updated_at": datetime.now(UTC),
        }
        try:
            changed = (
                self.db.query(JobProviderConfiguration)
                .filter(
                    JobProviderConfiguration.id == configuration_id,
                    JobProviderConfiguration.user_id == user_id,
                    JobProviderConfiguration.revision == payload.expected_revision,
                )
                .update(values, synchronize_session=False)
            )
            if changed != 1:
                self.db.rollback()
                raise ProviderConfigurationError(
                    "revision_conflict", "Provider changed; reread it before saving"
                )
            self.db.commit()
            self.db.expire_all()
        except IntegrityError as exc:
            self.db.rollback()
            raise ProviderConfigurationError(
                "provider_key_conflict", "A provider with this key already exists"
            ) from exc
        return self.get(user_id, configuration_id)

    def set_enabled(
        self,
        user_id: int,
        configuration_id: str,
        payload: ProviderStateUpdate,
    ) -> ProviderConfigurationView:
        current = self.get_row(user_id, configuration_id)
        if payload.enabled:
            if current.adapter_kind == "native":
                validate_native_adapter_id(current.native_adapter_id or "")
                if current.key != current.native_adapter_id:
                    raise ProviderConfigurationError(
                        "invalid_stored_configuration", "Stored provider configuration is invalid"
                    )
                ProviderCapabilitiesConfig.model_validate(current.capabilities_config)
            else:
                materialize_configuration(current)
        values: dict[Any, Any] = {
            "enabled": payload.enabled,
            "revision": payload.expected_revision + 1,
            "updated_at": datetime.now(UTC),
        }
        changed = (
            self.db.query(JobProviderConfiguration)
            .filter(
                JobProviderConfiguration.id == configuration_id,
                JobProviderConfiguration.user_id == user_id,
                JobProviderConfiguration.revision == payload.expected_revision,
            )
            .update(values, synchronize_session=False)
        )
        if changed != 1:
            self.db.rollback()
            if (
                self.db.query(JobProviderConfiguration.id)
                .filter(
                    JobProviderConfiguration.id == configuration_id,
                    JobProviderConfiguration.user_id == user_id,
                )
                .first()
            ):
                raise ProviderConfigurationError(
                    "revision_conflict", "Provider changed; reread it before changing state"
                )
            raise ProviderConfigurationError("provider_not_found", "Provider was not found")
        self.db.commit()
        self.db.expire_all()
        return self.get(user_id, configuration_id)

    def delete(self, user_id: int, configuration_id: str, *, expected_revision: int) -> None:
        changed = (
            self.db.query(JobProviderConfiguration)
            .filter(
                JobProviderConfiguration.id == configuration_id,
                JobProviderConfiguration.user_id == user_id,
                JobProviderConfiguration.revision == expected_revision,
            )
            .delete(synchronize_session=False)
        )
        if changed != 1:
            self.db.rollback()
            if (
                self.db.query(JobProviderConfiguration.id)
                .filter(
                    JobProviderConfiguration.id == configuration_id,
                    JobProviderConfiguration.user_id == user_id,
                )
                .first()
            ):
                raise ProviderConfigurationError(
                    "revision_conflict", "Provider changed; reread it before deleting"
                )
            raise ProviderConfigurationError("provider_not_found", "Provider was not found")
        self.db.commit()
