"""Focused provider definition schemas contracts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from .schema_validation import (
    _FIELD_PATH_RE,
    _HEADER_RE,
    _JSON_PATH_RE,
    _KEY_RE,
    CANONICAL_FIELDS,
    PRESERVE_SECRET,
    ProviderAdapterKind,
    ProviderMethod,
    ProviderRuntimeKind,
    StrictProviderModel,
    _validate_template,
    _validate_template_tree,
    normalize_printable,
)


class ProviderRequestConfig(StrictProviderModel):
    base_url: str = Field(min_length=12, max_length=2_048)
    path_template: str = Field(default="/", min_length=1, max_length=1_024)
    method: ProviderMethod = "GET"
    query_params: dict[str, str] = Field(default_factory=dict)
    json_body: dict[str, Any] | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=20, ge=1, le=60)
    max_response_bytes: int = Field(default=2_000_000, ge=1_024, le=8_388_608)
    max_pages: int = Field(default=5, ge=1, le=20)
    page_size: int = Field(default=50, ge=1, le=100)
    throttle_ms: int = Field(default=250, ge=0, le=10_000)
    retries: int = Field(default=1, ge=0, le=3)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        candidate = value.strip()
        parsed = urlsplit(candidate)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Provider base_url must be a credential-free HTTPS origin")
        if parsed.path not in {"", "/"}:
            raise ValueError("Put provider paths in path_template, not base_url")
        port = parsed.port
        if port not in {None, 443}:
            raise ValueError("Provider base_url must use the default HTTPS port")
        host = parsed.hostname.lower()
        return f"https://[{host}]" if ":" in host else f"https://{host}"

    @field_validator("path_template")
    @classmethod
    def validate_path_template(cls, value: str) -> str:
        if (
            not value.startswith("/")
            or value.startswith("//")
            or "://" in value
            or "#" in value
            or "?" in value
        ):
            raise ValueError("Provider path_template must be a same-origin absolute path")
        return _validate_template(value)

    @field_validator("query_params")
    @classmethod
    def validate_query_params(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 30:
            raise ValueError("At most 30 provider query parameters are allowed")
        for key, item in value.items():
            if not _FIELD_PATH_RE.fullmatch(key) or len(item) > 2_000:
                raise ValueError("Provider query parameters are invalid")
            _validate_template(item)
        return value

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 20:
            raise ValueError("At most 20 provider headers are allowed")
        normalized: dict[str, str] = {}
        forbidden = {"host", "content-length", "transfer-encoding", "connection", "accept-encoding"}
        for key, item in value.items():
            name = key.strip()
            if not _HEADER_RE.fullmatch(name) or name.casefold() in forbidden:
                raise ValueError("Provider header name is not allowed")
            if (
                not isinstance(item, str)
                or not 1 <= len(item) <= 2_048
                or "\r" in item
                or "\n" in item
            ):
                raise ValueError("Provider header value is invalid")
            normalized[name] = item if item == PRESERVE_SECRET else _validate_template(item)
        return normalized

    @field_validator("json_body")
    @classmethod
    def validate_json_body(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if value is None else _validate_template_tree(value)

    @model_validator(mode="after")
    def validate_method_body(self) -> "ProviderRequestConfig":
        if self.method == "GET" and self.json_body is not None:
            raise ValueError("GET providers cannot define a JSON body")
        return self

class ProviderFieldMapping(StrictProviderModel):
    source: str = Field(min_length=1, max_length=500)
    attribute: str | None = Field(default=None, max_length=80)
    default: str | None = Field(default=None, max_length=1_000)

    @field_validator("attribute")
    @classmethod
    def validate_attribute(cls, value: str | None) -> str | None:
        if value is not None and not _HEADER_RE.fullmatch(value):
            raise ValueError("HTML attribute mapping is invalid")
        return value

class ProviderExtractionConfig(StrictProviderModel):
    items_path: str | None = Field(default=None, max_length=500)
    item_selector: str | None = Field(default=None, max_length=500)
    total_path: str | None = Field(default=None, max_length=500)
    fields: dict[str, ProviderFieldMapping] = Field(min_length=2, max_length=20)

    @field_validator("items_path", "total_path")
    @classmethod
    def validate_json_path(cls, value: str | None) -> str | None:
        if value is not None and not _JSON_PATH_RE.fullmatch(value):
            raise ValueError("JSON extraction paths must be dotted object paths")
        return value

    @field_validator("fields")
    @classmethod
    def validate_fields(
        cls, value: dict[str, ProviderFieldMapping]
    ) -> dict[str, ProviderFieldMapping]:
        if not set(value).issubset(CANONICAL_FIELDS) or not {"id", "title"}.issubset(value):
            raise ValueError("Provider mappings require canonical id and title fields")
        return value

class ProviderCapabilitiesConfig(StrictProviderModel):
    accepted_domains: list[str] = Field(default_factory=lambda: ["*"], min_length=1, max_length=20)
    supported_languages: list[str] = Field(
        default_factory=lambda: ["en"], min_length=1, max_length=20
    )

    @field_validator("accepted_domains", "supported_languages")
    @classmethod
    def validate_tokens(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().lower() for item in value]
        if len(normalized) != len(set(normalized)) or any(
            not re.fullmatch(r"\*|[a-z][a-z0-9_-]{0,31}", item) for item in normalized
        ):
            raise ValueError("Provider capability values are invalid")
        return normalized

class ProviderConfigurationInput(StrictProviderModel):
    key: str = Field(min_length=2, max_length=64)
    display_name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    adapter_kind: ProviderAdapterKind
    enabled: bool = False
    request: ProviderRequestConfig
    extraction: ProviderExtractionConfig
    capabilities: ProviderCapabilitiesConfig = Field(default_factory=ProviderCapabilitiesConfig)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        candidate = value.strip().lower()
        if not _KEY_RE.fullmatch(candidate) or candidate in {
            "job_room",
            "swissdevjobs",
            "adecco",
            "local_db",
        }:
            raise ValueError("Provider key is invalid or reserved")
        return candidate

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalize_printable(value, maximum=160, label="Provider display name")

    @model_validator(mode="after")
    def validate_extraction_for_adapter(self) -> "ProviderConfigurationInput":
        if self.adapter_kind == "json":
            if not self.extraction.items_path or self.extraction.item_selector:
                raise ValueError("JSON providers require items_path and no item_selector")
            for mapping in self.extraction.fields.values():
                if mapping.attribute is not None or not _FIELD_PATH_RE.fullmatch(mapping.source):
                    raise ValueError("JSON field mappings must use dotted paths")
        else:
            if not self.extraction.item_selector or self.extraction.items_path:
                raise ValueError("HTML providers require item_selector and no items_path")
            if self.extraction.total_path:
                raise ValueError("HTML providers cannot define total_path")
        return self

class ProviderConfigurationCreate(ProviderConfigurationInput):
    pass

class ProviderConfigurationUpdate(ProviderConfigurationInput):
    expected_revision: int = Field(ge=1)

class ProviderConfigurationView(StrictProviderModel):
    id: str = Field(json_schema_extra={"format": "uuid"})
    key: str
    display_name: str
    description: str = ""
    adapter_kind: ProviderRuntimeKind
    enabled: bool
    revision: int = Field(ge=1)
    native_adapter_id: str | None = None
    source_pack_id: str | None = None
    source_pack_version: str | None = None
    request: ProviderRequestConfig | None = None
    extraction: ProviderExtractionConfig | None = None
    capabilities: ProviderCapabilitiesConfig = Field(default_factory=ProviderCapabilitiesConfig)
    has_secrets: bool = False
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_runtime_shape(self) -> "ProviderConfigurationView":
        if self.adapter_kind == "native":
            if not self.native_adapter_id or self.request is not None or self.extraction is not None:
                raise ValueError("Native provider rows require only a native adapter identifier")
            if self.has_secrets:
                raise ValueError("Native provider rows cannot contain configured secrets")
        elif (
            self.native_adapter_id is not None
            or self.request is None
            or self.extraction is None
        ):
            raise ValueError("Declarative provider rows require request and extraction contracts")
        return self

class ProviderValidationView(StrictProviderModel):
    valid: bool
    provider_key: str
    warnings: list[str] = Field(default_factory=list, max_length=20)

class ProviderTestRequest(StrictProviderModel):
    allow_network: Literal[True]
    query: str = Field(default="software engineer", max_length=1_000)
    location: str = Field(default="", max_length=500)
    language: str = Field(default="en", min_length=2, max_length=16)

    @field_validator("allow_network", mode="before")
    @classmethod
    def require_explicit_consent(cls, value: Any) -> bool:
        if value is not True:
            raise ValueError("Provider testing requires explicit network consent")
        return True

class ProviderTestView(StrictProviderModel):
    provider_key: str
    returned_count: int = Field(ge=0, le=5)
    sample: list[dict[str, Any]] = Field(max_length=5)
    diagnostics: list[str] = Field(default_factory=list, max_length=20)
