"""Validate portable provider records without granting network consent."""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.db.types import aware_utc
from backend.portability.archive import ArchiveError
from backend.providers.configuration.html_extract import validate_selector
from backend.providers.configuration.models import JobProviderConfiguration
from backend.providers.configuration.native import validate_native_adapter_id
from backend.providers.configuration.network_policy import validate_destination_literal
from backend.providers.configuration.schemas import (
    ProviderCapabilitiesConfig,
    ProviderConfigurationInput,
    secret_header,
)
from backend.providers.configuration.service import MAX_PROVIDERS_PER_USER


def validate_provider_records(decoded: dict[str, list[dict[str, Any]]]) -> None:
    if len(decoded["job_provider_configurations"]) > MAX_PROVIDERS_PER_USER:
        raise ArchiveError("Archive contains too many provider configurations")
    for row in decoded["job_provider_configurations"]:
        try:
            if row.get("adapter_kind") == "native":
                raw_adapter_id = row.get("native_adapter_id")
                if not isinstance(raw_adapter_id, str):
                    raise ValueError("Native provider rows require an adapter identifier")
                native_adapter_id = validate_native_adapter_id(raw_adapter_id)
                if row.get("key") != native_adapter_id:
                    raise ValueError("Native provider keys must match the reviewed adapter ID")
                if row.get("request_config") is not None or row.get("extraction_config") is not None:
                    raise ValueError("Native provider rows cannot contain declarative configuration")
                ProviderCapabilitiesConfig.model_validate(row.get("capabilities_config"))
                # Restore never grants network consent, including for reviewed native adapters.
                row["enabled"] = False
                continue
            request_config = row.get("request_config")
            headers = request_config.get("headers", {}) if isinstance(request_config, dict) else {}
            if not isinstance(headers, dict) or any(
                isinstance(name, str) and secret_header(name) for name in headers
            ):
                raise ValueError("Portable provider configurations cannot contain secrets")
            declaration = ProviderConfigurationInput.model_validate(
                {
                    "key": row.get("key"),
                    "display_name": row.get("display_name"),
                    "description": row.get("description"),
                    "adapter_kind": row.get("adapter_kind"),
                    "enabled": row.get("enabled"),
                    "request": request_config,
                    "extraction": row.get("extraction_config"),
                    "capabilities": row.get("capabilities_config"),
                }
            )
            validate_destination_literal(declaration.request.base_url)
            if declaration.adapter_kind == "html":
                validate_selector(declaration.extraction.item_selector or "")
                for mapping in declaration.extraction.fields.values():
                    if mapping.source != ".":
                        validate_selector(mapping.source)
            # Portable archives are integrity checked, not authenticated. Requiring an explicit
            # re-enable prevents a crafted archive from silently granting network consent.
            row["enabled"] = False
        except (ValueError, TypeError) as exc:
            raise ArchiveError("Archive provider configuration is invalid") from exc


def provider_restore_was_published(
    db: Session, user_id: int, expected: list[dict[str, Any]]
) -> bool:
    """Verify the complete destination-unique provider transaction identity."""
    ids = {row.get("id") for row in expected}
    if not expected or len(ids) != len(expected) or any(not isinstance(value, str) for value in ids):
        raise ValueError("Restore provider identity is unavailable")
    actual = db.query(JobProviderConfiguration).filter(JobProviderConfiguration.id.in_(ids)).all()
    if not actual:
        return False
    if len(actual) != len(expected) or any(row.user_id != user_id for row in actual):
        raise ValueError("Restore provider identity is inconsistent")
    if db.query(JobProviderConfiguration).filter_by(user_id=user_id).count() != len(expected):
        raise ValueError("Restore provider inventory is inconsistent")
    by_id = {row["id"]: row for row in expected}
    for row in actual:
        for column in JobProviderConfiguration.__table__.columns:
            value = getattr(row, column.name)
            wanted = user_id if column.name == "user_id" else by_id[row.id].get(column.name)
            if column.name in {"created_at", "updated_at"}:
                if not isinstance(value, datetime) or not isinstance(wanted, datetime):
                    raise ValueError("Restore provider timestamps are inconsistent")
                value = aware_utc(value)
                wanted = aware_utc(wanted)
            if value != wanted:
                raise ValueError("Restore provider contents are inconsistent")
    return True
