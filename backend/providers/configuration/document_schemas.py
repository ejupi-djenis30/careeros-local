"""Focused provider document schemas contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .definition_schemas import (
    ProviderCapabilitiesConfig,
    ProviderConfigurationInput,
    ProviderConfigurationView,
)
from .schema_validation import (
    _KEY_RE,
    _PACK_ID_RE,
    _PACK_VERSION_RE,
    StrictProviderModel,
    normalize_printable,
)


class DeclarativeProviderImportEntry(StrictProviderModel):
    kind: Literal["declarative"] = "declarative"
    configuration: ProviderConfigurationInput

    @model_validator(mode="after")
    def validate_shareable_configuration(self) -> "DeclarativeProviderImportEntry":
        if self.configuration.enabled:
            raise ValueError("Imported provider documents must not pre-enable network access")
        if self.configuration.request.headers:
            raise ValueError("Imported provider documents cannot contain configured headers")
        return self

class NativeProviderImportEntry(StrictProviderModel):
    kind: Literal["native"] = "native"
    adapter_id: str = Field(min_length=2, max_length=64)
    key: str = Field(min_length=2, max_length=64)
    display_name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    capabilities: ProviderCapabilitiesConfig = Field(default_factory=ProviderCapabilitiesConfig)

    @field_validator("adapter_id", "key")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        candidate = value.strip().lower()
        if not _KEY_RE.fullmatch(candidate):
            raise ValueError("Native provider identifier is invalid")
        return candidate

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalize_printable(value, maximum=160, label="Provider display name")

    @model_validator(mode="after")
    def require_canonical_key(self) -> "NativeProviderImportEntry":
        if self.key != self.adapter_id:
            raise ValueError("Native provider keys must match their adapter identifier")
        return self

ProviderImportEntry = Annotated[
    DeclarativeProviderImportEntry | NativeProviderImportEntry,
    Field(discriminator="kind"),
]

class ProviderDocument(StrictProviderModel):
    kind: Literal["provider"] = "provider"
    format_version: Literal[1] = 1
    provider: ProviderImportEntry

class ProviderPackDocument(StrictProviderModel):
    kind: Literal["provider_pack"] = "provider_pack"
    format_version: Literal[1] = 1
    id: str = Field(min_length=3, max_length=160)
    version: str = Field(min_length=5, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    providers: list[ProviderImportEntry] = Field(min_length=1, max_length=20)

    @field_validator("id")
    @classmethod
    def validate_pack_id(cls, value: str) -> str:
        candidate = value.strip().lower()
        if not _PACK_ID_RE.fullmatch(candidate):
            raise ValueError("Provider pack id is invalid")
        return candidate

    @field_validator("version")
    @classmethod
    def validate_pack_version(cls, value: str) -> str:
        candidate = value.strip()
        if not _PACK_VERSION_RE.fullmatch(candidate):
            raise ValueError("Provider pack version is invalid")
        return candidate

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_printable(value, maximum=160, label="Provider pack name")

    @model_validator(mode="after")
    def unique_provider_keys(self) -> "ProviderPackDocument":
        keys = [
            entry.configuration.key
            if isinstance(entry, DeclarativeProviderImportEntry)
            else entry.key
            for entry in self.providers
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("Provider pack keys must be unique")
        return self

ProviderImportDocument = Annotated[
    ProviderDocument | ProviderPackDocument,
    Field(discriminator="kind"),
]

class ProviderImportRequest(StrictProviderModel):
    document: ProviderImportDocument
    activate: bool = False

class ProviderPackInstallRequest(StrictProviderModel):
    activate: bool = False

class ProviderStateUpdate(StrictProviderModel):
    expected_revision: int = Field(ge=1)
    enabled: bool

class ProviderPackSummaryView(StrictProviderModel):
    id: str
    version: str
    name: str
    description: str
    provider_keys: list[str] = Field(max_length=20)

class ProviderImportResultView(StrictProviderModel):
    source_id: str | None
    activated: bool
    imported: list[ProviderConfigurationView] = Field(min_length=1, max_length=20)

class ProviderCatalogView(StrictProviderModel):
    installed: list[ProviderConfigurationView]
    available_packs: list[ProviderPackSummaryView]
