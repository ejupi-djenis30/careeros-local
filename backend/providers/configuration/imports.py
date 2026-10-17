"""Focused provider imports with service-owned atomic transactions."""

from __future__ import annotations

import builtins

from sqlalchemy.exc import IntegrityError

from backend.providers.configuration.models import JobProviderConfiguration
from backend.providers.configuration.native import validate_native_adapter_id
from backend.providers.configuration.schemas import (
    DeclarativeProviderImportEntry,
    NativeProviderImportEntry,
    ProviderDocument,
    ProviderImportDocument,
    ProviderImportResultView,
)

from .catalog import (
    MAX_PROVIDERS_PER_USER,
    ProviderCatalog,
    ProviderConfigurationError,
    configuration_view,
)

MAX_IMPORT_DOCUMENT_BYTES = 256 * 1024


class ProviderImports(ProviderCatalog):
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
