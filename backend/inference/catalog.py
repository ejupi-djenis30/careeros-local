from __future__ import annotations

import platform
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ALLOWED_DOWNLOAD_HOSTS = {"github.com", "huggingface.co"}


def _verified_https_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError("catalog downloads require an approved HTTPS origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("catalog download URLs cannot contain credentials, query, or fragment")
    return value


class RuntimeAsset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    archive_type: Literal["zip", "tar.gz"]
    url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    executable: str = Field(min_length=1, max_length=120)

    _url_is_approved = field_validator("url")(_verified_https_url)


class RuntimeCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["llama.cpp"]
    version: str = Field(pattern=r"^b[0-9]+$")
    license: str = Field(min_length=1, max_length=80)
    assets: dict[str, RuntimeAsset]


class ModelCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,80}$")
    display_name: str = Field(min_length=1, max_length=160)
    author: str = Field(min_length=1, max_length=120)
    license: str = Field(min_length=1, max_length=80)
    parameters: str = Field(min_length=1, max_length=40)
    quantization: str = Field(min_length=1, max_length=40)
    context_tokens: int = Field(ge=1024)
    recommended_context_tokens: int = Field(ge=1024)
    size_bytes: int = Field(gt=0)
    minimum_ram_bytes: int = Field(gt=0)
    recommended_ram_bytes: int = Field(gt=0)
    url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+\.gguf$")
    capabilities: tuple[str, ...]

    _url_is_approved = field_validator("url")(_verified_https_url)


class ModelCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    runtime: RuntimeCatalog
    models: tuple[ModelCatalogEntry, ...]

    def model(self, key: str) -> ModelCatalogEntry:
        for entry in self.models:
            if entry.key == key:
                return entry
        raise KeyError(f"Unknown managed model: {key}")


@lru_cache(maxsize=1)
def load_model_catalog() -> ModelCatalog:
    catalog_path = Path(__file__).with_name("model_catalog.json")
    return ModelCatalog.model_validate_json(catalog_path.read_text(encoding="utf-8"))


def current_platform_key() -> str:
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower()
    architecture = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
    key = f"{system}-{architecture}"
    if key not in load_model_catalog().runtime.assets:
        raise RuntimeError(f"Managed local inference is not packaged for {key}")
    return key


def public_catalog() -> dict[str, object]:
    catalog = load_model_catalog()
    return {
        "catalogVersion": catalog.catalog_version,
        "runtime": {
            "name": catalog.runtime.name,
            "version": catalog.runtime.version,
            "license": catalog.runtime.license,
        },
        "models": [
            {
                "key": item.key,
                "displayName": item.display_name,
                "author": item.author,
                "license": item.license,
                "parameters": item.parameters,
                "quantization": item.quantization,
                "contextTokens": item.context_tokens,
                "sizeBytes": item.size_bytes,
                "minimumRamBytes": item.minimum_ram_bytes,
                "recommendedRamBytes": item.recommended_ram_bytes,
                "capabilities": list(item.capabilities),
            }
            for item in catalog.models
        ],
    }
