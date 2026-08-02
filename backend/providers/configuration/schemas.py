"""Strict declarations and API views for configurable job providers."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProviderAdapterKind = Literal["json", "html"]
ProviderRuntimeKind = Literal["json", "html", "native"]
ProviderMethod = Literal["GET", "POST"]
CANONICAL_FIELDS = frozenset(
    {
        "id",
        "title",
        "description",
        "company",
        "location",
        "url",
        "application_url",
        "application_email",
        "posted_at",
        "workload_min",
        "workload_max",
        "country_code",
    }
)
ALLOWED_TEMPLATE_VARIABLES = frozenset(
    {
        "query",
        "location",
        "language",
        "page",
        "page_one_based",
        "page_size",
        "offset",
        "workload_min",
        "workload_max",
    }
)
PRESERVE_SECRET = "__CAREEROS_PRESERVE_SECRET__"
REDACTED_SECRET = "••••••••"
_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_HEADER_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,80}$")
_FIELD_PATH_RE = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")
_JSON_PATH_RE = re.compile(
    r"^(?:\$|(?:\$\.)?[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)$"
)
_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_PACK_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,159}$")
_PACK_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


class StrictProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def normalize_printable(value: str, *, maximum: int, label: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    if (
        not normalized
        or len(normalized) > maximum
        or any(unicodedata.category(character).startswith("C") for character in normalized)
    ):
        raise ValueError(f"{label} must contain printable text")
    return normalized


def secret_header(_name: str) -> bool:
    """Treat every user-supplied header value as confidential.

    Header-name heuristics are not a security boundary: providers routinely use custom names for
    API credentials. Redacting and omitting every configured header prevents an innocuous-looking
    name from leaking its value through API, MCP or portable archives.
    """

    return True


def _validate_template(value: str) -> str:
    unknown = set(_PLACEHOLDER_RE.findall(value)) - ALLOWED_TEMPLATE_VARIABLES
    if unknown or "{{" in value or "}}" in value:
        raise ValueError("Provider templates contain an unsupported variable")
    return value


def _validate_template_tree(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        raise ValueError("Provider body nesting is too deep")
    if isinstance(value, str):
        if len(value) > 2_000:
            raise ValueError("Provider template values are too long")
        return _validate_template(value)
    if isinstance(value, bool) or value is None or isinstance(value, int | float):
        return value
    if isinstance(value, list):
        if len(value) > 40:
            raise ValueError("Provider body lists are too large")
        return [_validate_template_tree(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 40 or not all(
            isinstance(key, str) and 1 <= len(key) <= 120 for key in value
        ):
            raise ValueError("Provider body objects are invalid")
        return {key: _validate_template_tree(item, depth=depth + 1) for key, item in value.items()}
    raise ValueError("Provider body values must be JSON-compatible")


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
        return f"https://{parsed.hostname.lower()}"

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
    query: str = Field(default="software engineer", max_length=1_000)
    location: str = Field(default="", max_length=500)
    language: str = Field(default="en", min_length=2, max_length=16)


class ProviderTestView(StrictProviderModel):
    provider_key: str
    returned_count: int = Field(ge=0, le=5)
    sample: list[dict[str, Any]] = Field(max_length=5)
    diagnostics: list[str] = Field(default_factory=list, max_length=20)


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
