"""CRUD, validation and redaction for declarative provider configurations."""

from __future__ import annotations

import builtins
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.providers.configuration.html_extract import validate_selector
from backend.providers.configuration.models import JobProviderConfiguration
from backend.providers.configuration.native import validate_native_adapter_id
from backend.providers.configuration.network_policy import validate_destination_literal
from backend.providers.configuration.schemas import (
    PRESERVE_SECRET,
    REDACTED_SECRET,
    DeclarativeProviderImportEntry,
    NativeProviderImportEntry,
    ProviderCapabilitiesConfig,
    ProviderConfigurationCreate,
    ProviderConfigurationInput,
    ProviderConfigurationUpdate,
    ProviderConfigurationView,
    ProviderDocument,
    ProviderImportDocument,
    ProviderImportResultView,
    ProviderRequestConfig,
    ProviderStateUpdate,
    ProviderValidationView,
    secret_header,
)

MAX_PROVIDERS_PER_USER = 50
MAX_IMPORT_DOCUMENT_BYTES = 256 * 1024


class ProviderConfigurationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _validate_declaration(payload: ProviderConfigurationInput) -> None:
    validate_destination_literal(payload.request.base_url)
    if payload.adapter_kind == "html":
        validate_selector(payload.extraction.item_selector or "")
        for mapping in payload.extraction.fields.values():
            if mapping.source != ".":
                validate_selector(mapping.source)


def _redacted_request(config: ProviderRequestConfig) -> tuple[ProviderRequestConfig, bool]:
    has_secrets = any(secret_header(name) for name in config.headers)
    headers = {
        name: REDACTED_SECRET if secret_header(name) else value
        for name, value in config.headers.items()
    }
    return config.model_copy(update={"headers": headers}), has_secrets


def configuration_view(row: JobProviderConfiguration) -> ProviderConfigurationView:
    try:
        capabilities = ProviderCapabilitiesConfig.model_validate(row.capabilities_config)
        if row.adapter_kind == "native":
            validate_native_adapter_id(row.native_adapter_id or "")
            return ProviderConfigurationView.model_validate(
                {
                    "id": row.id,
                    "key": row.key,
                    "display_name": row.display_name,
                    "description": row.description,
                    "adapter_kind": "native",
                    "native_adapter_id": row.native_adapter_id,
                    "source_pack_id": row.source_pack_id,
                    "source_pack_version": row.source_pack_version,
                    "enabled": row.enabled,
                    "revision": row.revision,
                    "request": None,
                    "extraction": None,
                    "capabilities": capabilities,
                    "has_secrets": False,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
            )
        request = ProviderRequestConfig.model_validate(row.request_config)
        redacted_request, has_secrets = _redacted_request(request)
        return ProviderConfigurationView.model_validate(
            {
                "id": row.id,
                "key": row.key,
                "display_name": row.display_name,
                "description": row.description,
                "adapter_kind": row.adapter_kind,
                "native_adapter_id": None,
                "source_pack_id": row.source_pack_id,
                "source_pack_version": row.source_pack_version,
                "enabled": row.enabled,
                "revision": row.revision,
                "request": redacted_request,
                "extraction": row.extraction_config,
                "capabilities": capabilities,
                "has_secrets": has_secrets,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )
    except ValidationError as exc:
        raise ProviderConfigurationError(
            "invalid_stored_configuration", "Stored provider configuration is invalid"
        ) from exc


def materialize_configuration(row: JobProviderConfiguration) -> ProviderConfigurationInput:
    if row.adapter_kind == "native":
        raise ProviderConfigurationError(
            "native_provider_not_declarative", "Native provider has no declarative request contract"
        )
    try:
        payload = ProviderConfigurationInput.model_validate(
            {
                "key": row.key,
                "display_name": row.display_name,
                "description": row.description,
                "adapter_kind": row.adapter_kind,
                "enabled": row.enabled,
                "request": row.request_config,
                "extraction": row.extraction_config,
                "capabilities": row.capabilities_config,
            }
        )
        _validate_declaration(payload)
        return payload
    except (ValidationError, ValueError) as exc:
        raise ProviderConfigurationError(
            "invalid_stored_configuration", "Stored provider configuration is invalid"
        ) from exc


class ProviderConfigurationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, user_id: int) -> list[ProviderConfigurationView]:
        rows = (
            self.db.query(JobProviderConfiguration)
            .filter(JobProviderConfiguration.user_id == user_id)
            .order_by(
                JobProviderConfiguration.display_name.asc(), JobProviderConfiguration.id.asc()
            )
            .limit(MAX_PROVIDERS_PER_USER)
            .all()
        )
        return [configuration_view(row) for row in rows]

    def rows(
        self, user_id: int, *, enabled_only: bool = False
    ) -> Sequence[JobProviderConfiguration]:
        query = self.db.query(JobProviderConfiguration).filter(
            JobProviderConfiguration.user_id == user_id
        )
        if enabled_only:
            query = query.filter(JobProviderConfiguration.enabled.is_(True))
        return (
            query.order_by(JobProviderConfiguration.key.asc())
            .limit(MAX_PROVIDERS_PER_USER)
            .all()
        )

    def get_row(self, user_id: int, configuration_id: str) -> JobProviderConfiguration:
        row = (
            self.db.query(JobProviderConfiguration)
            .filter(
                JobProviderConfiguration.id == configuration_id,
                JobProviderConfiguration.user_id == user_id,
            )
            .one_or_none()
        )
        if row is None:
            raise ProviderConfigurationError("provider_not_found", "Provider was not found")
        return row

    def get(self, user_id: int, configuration_id: str) -> ProviderConfigurationView:
        return configuration_view(self.get_row(user_id, configuration_id))

    def validate(self, payload: ProviderConfigurationInput) -> ProviderValidationView:
        _validate_declaration(payload)
        warnings: list[str] = []
        if payload.enabled and not payload.description:
            warnings.append("Add a description so search routing can explain this source")
        if "description" not in payload.extraction.fields:
            warnings.append("Jobs without a description may provide weaker verified analysis")
        return ProviderValidationView(valid=True, provider_key=payload.key, warnings=warnings)

    @staticmethod
    def _document_entries(
        document: ProviderImportDocument,
    ) -> tuple[
        builtins.list[DeclarativeProviderImportEntry | NativeProviderImportEntry],
        str | None,
        str | None,
    ]:
        if isinstance(document, ProviderDocument):
            return [document.provider], None, None
        return list(document.providers), document.id, document.version

    def import_document(
        self,
        user_id: int,
        document: ProviderImportDocument,
        *,
        activate: bool = False,
    ) -> ProviderImportResultView:
        serialized = document.model_dump_json().encode("utf-8")
        if len(serialized) > MAX_IMPORT_DOCUMENT_BYTES:
            raise ProviderConfigurationError(
                "provider_import_too_large", "Provider import document is too large"
            )
        entries, source_pack_id, source_pack_version = self._document_entries(document)
        existing_count = (
            self.db.query(JobProviderConfiguration)
            .filter(JobProviderConfiguration.user_id == user_id)
            .count()
        )
        if existing_count + len(entries) > MAX_PROVIDERS_PER_USER:
            raise ProviderConfigurationError(
                "provider_limit",
                f"At most {MAX_PROVIDERS_PER_USER} providers are allowed",
            )

        keys = [
            entry.configuration.key
            if isinstance(entry, DeclarativeProviderImportEntry)
            else entry.key
            for entry in entries
        ]
        conflicts = (
            self.db.query(JobProviderConfiguration.key)
            .filter(
                JobProviderConfiguration.user_id == user_id,
                JobProviderConfiguration.key.in_(keys),
            )
            .all()
        )
        if conflicts:
            raise ProviderConfigurationError(
                "provider_key_conflict", "An imported provider key already exists"
            )

        rows: builtins.list[JobProviderConfiguration] = []
        for entry in entries:
            if isinstance(entry, DeclarativeProviderImportEntry):
                declaration = entry.configuration.model_copy(update={"enabled": activate})
                self.validate(declaration)
                row = JobProviderConfiguration(
                    user_id=user_id,
                    key=declaration.key,
                    display_name=declaration.display_name,
                    description=declaration.description,
                    adapter_kind=declaration.adapter_kind,
                    native_adapter_id=None,
                    source_pack_id=source_pack_id,
                    source_pack_version=source_pack_version,
                    enabled=activate,
                    revision=1,
                    request_config=declaration.request.model_dump(mode="json"),
                    extraction_config=declaration.extraction.model_dump(mode="json"),
                    capabilities_config=declaration.capabilities.model_dump(mode="json"),
                )
            else:
                validate_native_adapter_id(entry.adapter_id)
                row = JobProviderConfiguration(
                    user_id=user_id,
                    key=entry.key,
                    display_name=entry.display_name,
                    description=entry.description,
                    adapter_kind="native",
                    native_adapter_id=entry.adapter_id,
                    source_pack_id=source_pack_id,
                    source_pack_version=source_pack_version,
                    enabled=activate,
                    revision=1,
                    request_config=None,
                    extraction_config=None,
                    capabilities_config=entry.capabilities.model_dump(mode="json"),
                )
            rows.append(row)

        try:
            self.db.add_all(rows)
            self.db.commit()
            for row in rows:
                self.db.refresh(row)
        except IntegrityError as exc:
            self.db.rollback()
            raise ProviderConfigurationError(
                "provider_key_conflict", "An imported provider key already exists"
            ) from exc
        return ProviderImportResultView(
            source_id=source_pack_id,
            activated=activate,
            imported=[configuration_view(row) for row in rows],
        )

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
        stored_headers = ProviderRequestConfig.model_validate(current.request_config).headers
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
