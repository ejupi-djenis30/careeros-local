"""User-scoped provider reads, validation and confidential response views."""

from __future__ import annotations

from collections.abc import Sequence

import httpx
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.providers.configuration.html_extract import validate_selector
from backend.providers.configuration.models import JobProviderConfiguration
from backend.providers.configuration.native import validate_native_adapter_id
from backend.providers.configuration.network_policy import validate_destination_literal
from backend.providers.configuration.schemas import (
    REDACTED_SECRET,
    ProviderCapabilitiesConfig,
    ProviderConfigurationInput,
    ProviderConfigurationView,
    ProviderRequestConfig,
    ProviderValidationView,
    secret_header,
)

MAX_PROVIDERS_PER_USER = 50


class ProviderConfigurationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _provider_origin(base_url: str) -> tuple[str, bytes, int | None]:
    """Match the origin used by HTTPX, including IDNA and effective HTTPS ports."""
    url = httpx.URL(base_url)
    default_port = {"http": 80, "https": 443}.get(url.scheme)
    return url.scheme, url.raw_host, url.port if url.port is not None else default_port


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


class ProviderCatalog:
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
            query.order_by(JobProviderConfiguration.key.asc()).limit(MAX_PROVIDERS_PER_USER).all()
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
