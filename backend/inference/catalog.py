from __future__ import annotations

import hashlib
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

    @field_validator("executable")
    @classmethod
    def executable_is_a_filename(cls, value: str) -> str:
        if value in {".", ".."} or any(char in value for char in ("/", "\\", ":")):
            raise ValueError("runtime executable must be a plain filename")
        return value


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
    signature_path = catalog_path.with_suffix(".sha256")
    return load_verified_catalog(catalog_path, signature_path)


def verify_file_sha256(path: Path, expected_sha256: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256.casefold():
        raise ValueError(f"SHA-256 verification failed for {path.name}")


def load_verified_catalog(catalog_path: Path, signature_path: Path) -> ModelCatalog:
    signature = signature_path.read_text(encoding="ascii").strip().split()
    if len(signature) != 2 or signature[1] != catalog_path.name:
        raise ValueError("model catalog signature file is malformed")
    expected = signature[0].casefold()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise ValueError("model catalog signature is not a SHA-256 digest")
    verify_file_sha256(catalog_path, expected)
    return ModelCatalog.model_validate_json(catalog_path.read_text(encoding="utf-8"))


def current_platform_key(
    *, system_name: str | None = None, machine_name: str | None = None
) -> str:
    system_value = system_name or sys.platform
    system = {"win32": "windows", "darwin": "macos"}.get(system_value, "linux")
    machine = (machine_name or platform.machine()).lower()
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
