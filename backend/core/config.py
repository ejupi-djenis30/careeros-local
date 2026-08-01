import json
import logging
import math
import os
import re
from ipaddress import ip_address
from pathlib import Path
from typing import Any, List, Literal, Optional
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure
from backend.db.sqlite import path_is_within, sqlite_database_path
from backend.inference.endpoint import validate_local_inference_url
from backend.storage.private_secret import (
    InstallationSecretError,
    read_installation_secret_file,
)

logger = logging.getLogger(__name__)
_SUPPORTED_TAURI_ORIGIN = "tauri://localhost"
_PRODUCTION_HTTP_CORS_HOSTS = {"localhost", "127.0.0.1", "::1", "tauri.localhost"}
_DNS_HOST_PATTERN = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)"
    r"(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*\Z"
)


def _normalize_cors_origin(value: str) -> str:
    """Return one canonical, credential-safe browser origin."""
    candidate = value.strip()
    if (
        not candidate
        or "*" in candidate
        or "\\" in candidate
        or any(character.isspace() for character in candidate)
    ):
        raise ValueError("CORS_ORIGINS contains an invalid exact origin")
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("CORS_ORIGINS contains an invalid exact origin") from exc
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or not parsed.hostname
        or "%" in parsed.hostname
    ):
        raise ValueError("CORS_ORIGINS contains an invalid exact origin")

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower()
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    if ":" in hostname:
        hostname = f"[{hostname}]"
    authority = hostname if port is None else f"{hostname}:{port}"
    origin = f"{scheme}://{authority}"
    if scheme in {"http", "https"}:
        return origin
    if origin == _SUPPORTED_TAURI_ORIGIN:
        return origin
    raise ValueError("CORS_ORIGINS contains an unsupported origin scheme")


def _parse_cors_origins(value: str | None) -> list[str]:
    if not value:
        return []
    if value.startswith("["):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("CORS_ORIGINS must contain valid JSON") from exc
        if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
            raise ValueError("CORS_ORIGINS JSON must be an array of strings")
        entries = decoded
    else:
        entries = value.split(",")
    if not entries or any(not item.strip() for item in entries):
        raise ValueError("CORS_ORIGINS must not contain empty origins")

    origins = [_normalize_cors_origin(item) for item in entries]
    if len(origins) != len(set(origins)):
        raise ValueError("CORS_ORIGINS must not contain duplicate origins")
    return origins


def _normalize_allowed_host(value: str) -> str:
    candidate = value.strip()
    if (
        not candidate
        or candidate != value
        or "*" in candidate
        or any(character.isspace() for character in candidate)
        or any(marker in candidate for marker in ("://", "/", "\\", "@", "?", "#"))
    ):
        raise ValueError("ALLOWED_HOSTS contains an invalid canonical host")
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    try:
        return ip_address(candidate).compressed.lower()
    except ValueError:
        normalized = candidate.lower()
        if ":" in normalized or not _DNS_HOST_PATTERN.fullmatch(normalized):
            raise ValueError("ALLOWED_HOSTS contains an invalid canonical host")
        return normalized


def _local_secret_default() -> str:
    """Load the installation secret for zero-config local container commands."""
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    secret_path = Path(os.environ.get("CAREEROS_SECRET_FILE", data_dir / ".secret-key"))
    try:
        return read_installation_secret_file(secret_path, trusted_root=secret_path.parent)
    except (InstallationSecretError, OSError):
        return "local-development-only"


class Settings(BaseSettings):
    """Local-first runtime settings.

    No cloud provider, API key or remote inference fallback is accepted here. Job-source
    egress is configured separately by source adapters and is never an inference path.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    API_V1_STR: Literal["/api/v1"] = "/api/v1"
    PROJECT_NAME: str = "CareerOS Local"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    OFFLINE_MODE: bool = False

    CORS_ORIGINS: Optional[str] = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"
    )
    # Credentialed browser origins are exact by default. Trusting every process
    # listening on an arbitrary localhost port would let an unrelated local web
    # app read refresh responses and cross the authenticated desktop boundary.
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1", "testserver"]

    DATABASE_URL: str = "sqlite:///./data/careeros.db"
    DATA_DIR: str = "data"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    SQLITE_BUSY_TIMEOUT_MS: int = 5000

    SECRET_KEY: str = Field(default_factory=_local_secret_default)
    ALGORITHM: Literal["HS256"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # The only supported inference runtime is a host explicitly considered local.
    LOCAL_INFERENCE_ALLOWED_HOSTS: str = "localhost,127.0.0.1,::1,ollama,host.docker.internal"
    LOCAL_INFERENCE_URL: str = "http://127.0.0.1:11434"
    LOCAL_MODEL: str = "qwen3:1.7b"
    LOCAL_INFERENCE_CONNECT_TIMEOUT_SECONDS: float = 2.0
    LOCAL_INFERENCE_REQUEST_TIMEOUT_SECONDS: float = 180.0

    # Local model identity. Per-step fields may be empty but cannot select a model other than
    # LOCAL_MODEL, so one readiness attestation covers every analysis workflow.
    LLM_CONTEXT_WINDOW: int = 8192
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.2
    LLM_TOP_P: float = 0.9
    LLM_PLAN_MODEL: str = ""
    LLM_MATCH_MODEL: str = ""
    LLM_NORMALIZE_MODEL: str = ""
    LLM_NORMALIZE_PROFILE_MODEL: str = ""
    LLM_COMPRESS_MODEL: str = ""
    LLM_CRITIQUE_MODEL: str = ""
    LLM_RERANK_MODEL: str = ""
    LLM_PLAN_CONTEXT_WINDOW: int = 0
    LLM_MATCH_CONTEXT_WINDOW: int = 0
    LLM_NORMALIZE_CONTEXT_WINDOW: int = 0
    LLM_NORMALIZE_PROFILE_CONTEXT_WINDOW: int = 0
    LLM_COMPRESS_CONTEXT_WINDOW: int = 0
    LLM_CRITIQUE_CONTEXT_WINDOW: int = 0
    LLM_RERANK_CONTEXT_WINDOW: int = 0
    LLM_PLAN_TEMPERATURE: Optional[float] = None
    LLM_MATCH_TEMPERATURE: Optional[float] = None
    LLM_NORMALIZE_TEMPERATURE: Optional[float] = None
    LLM_NORMALIZE_PROFILE_TEMPERATURE: Optional[float] = None
    LLM_COMPRESS_TEMPERATURE: Optional[float] = None
    LLM_CRITIQUE_TEMPERATURE: Optional[float] = None
    LLM_RERANK_TEMPERATURE: Optional[float] = None
    LLM_PLAN_TOP_P: Optional[float] = None
    LLM_MATCH_TOP_P: Optional[float] = None
    LLM_NORMALIZE_TOP_P: Optional[float] = None
    LLM_NORMALIZE_PROFILE_TOP_P: Optional[float] = None
    LLM_COMPRESS_TOP_P: Optional[float] = None
    LLM_CRITIQUE_TOP_P: Optional[float] = None
    LLM_RERANK_TOP_P: Optional[float] = None
    LLM_PLAN_MAX_TOKENS: Optional[int] = None
    LLM_MATCH_MAX_TOKENS: Optional[int] = None
    LLM_NORMALIZE_MAX_TOKENS: Optional[int] = None
    LLM_NORMALIZE_PROFILE_MAX_TOKENS: Optional[int] = None
    LLM_COMPRESS_MAX_TOKENS: Optional[int] = None
    LLM_CRITIQUE_MAX_TOKENS: Optional[int] = None
    LLM_RERANK_MAX_TOKENS: Optional[int] = None

    LLM_CALL_TIMEOUT_PLAN: int = 60
    LLM_CALL_TIMEOUT_NORMALIZE: int = 90
    LLM_CALL_TIMEOUT_MATCH: int = 120
    LLM_CALL_TIMEOUT_COACH: int = 60
    LLM_CALL_TIMEOUT_CRITIQUE: int = 90
    LLM_CALL_TIMEOUT_RERANK: int = 60
    LLM_PLAN_RETRY_ATTEMPTS: int = 2
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 30

    JOB_ROOM_USER_AGENT: str = "CareerOS-Local/2.0"
    MAX_UPLOAD_FILE_SIZE: int = 10 * 1024 * 1024
    HTTP_REQUEST_BODY_MAX_BYTES: int = 11 * 1024 * 1024
    PORTABLE_ARCHIVE_REQUEST_BODY_MAX_BYTES: int = 129 * 1024 * 1024
    CV_IMPORT_MAX_PAGES: int = 100
    CV_IMPORT_MAX_EXTRACTED_CHARS: int = 500_000
    SOURCE_IMPORT_MAX_PAGES: int = 250
    SOURCE_IMPORT_MAX_EXTRACTED_CHARS: int = 2_000_000
    SOURCE_IMPORT_MAX_ARCHIVE_MEMBERS: int = 2_000
    SOURCE_IMPORT_MAX_UNCOMPRESSED_BYTES: int = 64 * 1024 * 1024
    RESUME_MAX_PAGES: int = 3
    RESUME_PHOTO_MAX_PIXELS: int = 25_000_000
    RESUME_PHOTO_EDGE_PX: int = 720
    # Restore currently verifies an in-memory ZIP plus verified members. Keep
    # the combined worst-case footprint bounded for ordinary desktop hardware.
    PORTABLE_ARCHIVE_MAX_BYTES: int = 128 * 1024 * 1024
    PORTABLE_ARCHIVE_MAX_UNCOMPRESSED_BYTES: int = 256 * 1024 * 1024
    PORTABLE_ARCHIVE_MAX_MEMBERS: int = 5_000
    PORTABLE_ARCHIVE_MAX_RECORDS: int = 100_000
    MAX_DESCRIPTION_CHARS: int = 64_000
    SEARCH_EXECUTION_MODE: str = "sequential"
    SEARCH_CONCURRENCY: int = 3
    ANALYSIS_CONCURRENCY: int = 2
    ANALYSIS_BATCH_SIZE: int = 3
    NORMALIZE_BATCH_SIZE: int = 5
    MAX_CONCURRENT_SEARCHES_PER_USER: int = 1
    SEARCH_PIPELINE_TIMEOUT_SECONDS: int = 1800
    ADECCO_DETAIL_CONCURRENCY: int = 2

    MATCH_PROMPT_TARGET_CHARS: int = 7000
    MATCH_PROMPT_JOB_MAX_DESCRIPTION_CHARS: int = 1800
    NORMALIZE_PROMPT_TARGET_CHARS: int = 9000
    NORMALIZE_PROMPT_JOB_MAX_DESCRIPTION_CHARS: int = 2400
    PROMPT_COMPACTION_MAX_FRAGMENTS: int = 12
    SEARCH_COMPACT_DESCRIPTION_CACHE_MAX_CHARS: int = 1400
    SEARCH_PROFILE_SNAPSHOT_MAX_CHARS: int = 1000
    SEARCH_PLAN_ENABLE_LOOSE_DEDUP: bool = True
    SEARCH_ENABLE_DEGRADED_PLAN_FALLBACK: bool = True
    SEARCH_DEGRADED_PLAN_MAX_QUERIES: int = 3
    SEARCH_DEGRADED_PLAN_MAX_KEYWORDS: int = 2

    SEARCH_LOW_CONTEXT_MODE: str = "auto"
    SEARCH_LOW_CONTEXT_CONTEXT_WINDOW_THRESHOLD: int = 6000
    LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE: float = 3.6
    SEARCH_STANDARD_PROMPT_INPUT_RATIO: float = 0.42
    SEARCH_LOW_CONTEXT_PROMPT_INPUT_RATIO: float = 0.28
    SEARCH_LOW_CONTEXT_ANALYSIS_BATCH_SIZE: int = 1
    SEARCH_LOW_CONTEXT_NORMALIZE_BATCH_SIZE: int = 2
    SEARCH_LOW_CONTEXT_MATCH_PROMPT_TARGET_CHARS: int = 3600
    SEARCH_LOW_CONTEXT_NORMALIZE_PROMPT_TARGET_CHARS: int = 4200
    SEARCH_LOW_CONTEXT_MATCH_JOB_MAX_DESCRIPTION_CHARS: int = 900
    SEARCH_LOW_CONTEXT_NORMALIZE_JOB_MAX_DESCRIPTION_CHARS: int = 1200
    SEARCH_LOW_CONTEXT_PROFILE_SNAPSHOT_MAX_CHARS: int = 700

    SEARCH_ENABLE_NORMALIZATION_MATCHING: bool = True
    SEARCH_NORMALIZATION_EXPERIENCE_TOLERANCE: int = 3
    NORMALIZATION_RENORMALIZE_ENABLED: bool = True
    NORMALIZATION_CONFIDENCE_TIER1_THRESHOLD: float = 0.70
    NORMALIZATION_CONFIDENCE_TIER2_THRESHOLD: float = 0.40
    STRUCTURED_PRESCORE_ENABLED: bool = True
    STRUCTURED_PRESCORE_THRESHOLD: float = 30.0
    STRUCTURED_PRESCORE_THRESHOLD_WITH_PREFS: float = 35.0
    MATCH_CRITIQUE_ENABLED: bool = False
    MATCH_CRITIQUE_SCORE_RANGE_MIN: int = 40
    MATCH_CRITIQUE_SCORE_RANGE_MAX: int = 80
    MATCH_RERANK_ENABLED: bool = False
    MATCH_RERANK_TOP_N: int = 20
    RED_FLAGS_DETECTION_ENABLED: bool = True
    RECENCY_WEIGHTING_ENABLED: bool = True
    RECENCY_DECAY_HALFLIFE_DAYS: int = 30
    MATCH_ENABLE_PREFERENCE_INJECTION: bool = True
    PREFERENCE_MIN_SIGNAL_COUNT: int = 10
    PREFERENCE_PRESCORE_ENABLED: bool = True
    DEALBREAKER_ESCALATION_TIER1: int = 3
    DEALBREAKER_ESCALATION_TIER2: int = 6
    DEALBREAKER_ESCALATION_TIER3: int = 10
    SWISS_IMPLICIT_LANGUAGE_ENABLED: bool = True
    SALARY_BENCHMARK_ENABLED: bool = True

    # Embeddings are deterministic by default. A local model path may be configured later;
    # a registry name is never downloaded automatically.
    SKILL_EMBEDDING_ENABLED: bool = False
    SKILL_EMBEDDING_THRESHOLD: float = 0.65
    SKILL_EMBEDDING_MODEL: str = ""

    @property
    def cors_origins_list(self) -> List[str]:
        return _parse_cors_origins(self.CORS_ORIGINS)

    @property
    def local_inference_allowed_hosts(self) -> set[str]:
        return {
            item.strip().lower().strip("[]")
            for item in self.LOCAL_INFERENCE_ALLOWED_HOSTS.split(",")
            if item.strip()
        }

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, value: Any) -> List[str]:
        if isinstance(value, str):
            if value.startswith("["):
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError) as exc:
                    raise ValueError("ALLOWED_HOSTS must contain valid JSON") from exc
            else:
                value = value.split(",")
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError("ALLOWED_HOSTS must be a list of host strings")
        normalized = [_normalize_allowed_host(item) for item in value]
        if not normalized:
            raise ValueError("ALLOWED_HOSTS must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("ALLOWED_HOSTS must not contain duplicate hosts")
        return normalized

    @model_validator(mode="after")
    def validate_local_first_settings(self) -> "Settings":
        database_path = sqlite_database_path(self.DATABASE_URL)
        if self.ENVIRONMENT == "production":
            if database_path is None:
                raise ValueError("Production DATABASE_URL must use a file-backed SQLite vault")
            data_root = Path(self.DATA_DIR).expanduser().resolve(strict=False)
            if not path_is_within(database_path, data_root):
                raise ValueError("Production DATABASE_URL must stay inside DATA_DIR")
        try:
            cors_origins = self.cors_origins_list
        except ValueError as exc:
            if self.ENVIRONMENT == "production":
                raise ValueError("CORS_ORIGINS must contain unique exact browser origins") from exc
            diagnostic = diagnose_failure(exc, FailureCode.RUNTIME_POLICY_FALLBACK)
            log_failure(logger, diagnostic, level=logging.WARNING)
            # Development also fails closed: a malformed allowlist enables no
            # credentialed browser origins instead of partially trusting input.
            self.CORS_ORIGINS = None
            cors_origins = []
        if self.ENVIRONMENT == "production":
            for origin in cors_origins:
                parsed_origin = urlsplit(origin)
                if (
                    parsed_origin.scheme == "http"
                    and parsed_origin.hostname not in _PRODUCTION_HTTP_CORS_HOSTS
                ):
                    raise ValueError(
                        "Production CORS_ORIGINS must use HTTPS outside supported local origins"
                    )
        self.LOCAL_INFERENCE_URL = validate_local_inference_url(
            self.LOCAL_INFERENCE_URL,
            allowed_hosts=self.local_inference_allowed_hosts,
        )
        for field_name in (
            "LOCAL_INFERENCE_CONNECT_TIMEOUT_SECONDS",
            "LOCAL_INFERENCE_REQUEST_TIMEOUT_SECONDS",
            "LLM_CALL_TIMEOUT_PLAN",
            "LLM_CALL_TIMEOUT_NORMALIZE",
            "LLM_CALL_TIMEOUT_MATCH",
            "LLM_CALL_TIMEOUT_COACH",
            "LLM_CALL_TIMEOUT_CRITIQUE",
            "LLM_CALL_TIMEOUT_RERANK",
        ):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be greater than zero and finite")

        if not 1_024 <= self.LLM_CONTEXT_WINDOW <= 1_048_576 or not 1 <= self.LLM_MAX_TOKENS <= min(
            self.LLM_CONTEXT_WINDOW, 131_072
        ):
            raise ValueError(
                "LLM_CONTEXT_WINDOW and LLM_MAX_TOKENS must define a bounded valid context"
            )
        if (
            not self.LOCAL_MODEL
            or len(self.LOCAL_MODEL) > 256
            or any(ord(character) < 32 or ord(character) == 127 for character in self.LOCAL_MODEL)
        ):
            raise ValueError("LOCAL_MODEL must be a non-empty safe model identifier")

        step_names = (
            "PLAN",
            "MATCH",
            "NORMALIZE",
            "NORMALIZE_PROFILE",
            "COMPRESS",
            "CRITIQUE",
            "RERANK",
        )
        for field_name in (
            "LLM_TEMPERATURE",
            *(f"LLM_{step}_TEMPERATURE" for step in step_names),
        ):
            configured = getattr(self, field_name)
            if configured is None:
                continue
            value = float(configured)
            if not math.isfinite(value) or not 0 <= value <= 2:
                raise ValueError(f"{field_name} must be finite and between 0 and 2")
        for field_name in (
            "LLM_TOP_P",
            *(f"LLM_{step}_TOP_P" for step in step_names),
        ):
            configured = getattr(self, field_name)
            if configured is None:
                continue
            value = float(configured)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be finite and between 0 and 1")

        for step in step_names:
            context_override = int(getattr(self, f"LLM_{step}_CONTEXT_WINDOW"))
            if context_override != 0 and not 1_024 <= context_override <= 1_048_576:
                raise ValueError(
                    f"LLM_{step}_CONTEXT_WINDOW must be zero or between 1024 and 1048576"
                )
            context_window = context_override or self.LLM_CONTEXT_WINDOW
            token_override = getattr(self, f"LLM_{step}_MAX_TOKENS")
            max_tokens = self.LLM_MAX_TOKENS if token_override is None else int(token_override)
            if not 1 <= max_tokens <= min(context_window, 131_072):
                raise ValueError(
                    f"LLM_{step}_MAX_TOKENS must fit inside its bounded context window"
                )

        resource_ceilings = {
            "MAX_UPLOAD_FILE_SIZE": 64 * 1024 * 1024,
            "HTTP_REQUEST_BODY_MAX_BYTES": 128 * 1024 * 1024,
            "PORTABLE_ARCHIVE_REQUEST_BODY_MAX_BYTES": 640 * 1024 * 1024,
            "CV_IMPORT_MAX_PAGES": 1_000,
            "CV_IMPORT_MAX_EXTRACTED_CHARS": 5_000_000,
            "SOURCE_IMPORT_MAX_PAGES": 2_000,
            "SOURCE_IMPORT_MAX_EXTRACTED_CHARS": 10_000_000,
            "SOURCE_IMPORT_MAX_ARCHIVE_MEMBERS": 10_000,
            "SOURCE_IMPORT_MAX_UNCOMPRESSED_BYTES": 256 * 1024 * 1024,
            "RESUME_MAX_PAGES": 20,
            "RESUME_PHOTO_MAX_PIXELS": 100_000_000,
            "RESUME_PHOTO_EDGE_PX": 4_096,
            "PORTABLE_ARCHIVE_MAX_BYTES": 512 * 1024 * 1024,
            "PORTABLE_ARCHIVE_MAX_UNCOMPRESSED_BYTES": 1024 * 1024 * 1024,
            "PORTABLE_ARCHIVE_MAX_MEMBERS": 20_000,
            "PORTABLE_ARCHIVE_MAX_RECORDS": 1_000_000,
        }
        for field_name, ceiling in resource_ceilings.items():
            value = int(getattr(self, field_name))
            if not 1 <= value <= ceiling:
                raise ValueError(f"{field_name} must be between 1 and {ceiling}")
        if self.SOURCE_IMPORT_MAX_UNCOMPRESSED_BYTES < self.MAX_UPLOAD_FILE_SIZE:
            raise ValueError("SOURCE_IMPORT_MAX_UNCOMPRESSED_BYTES must cover MAX_UPLOAD_FILE_SIZE")
        if self.HTTP_REQUEST_BODY_MAX_BYTES <= self.MAX_UPLOAD_FILE_SIZE:
            raise ValueError("HTTP_REQUEST_BODY_MAX_BYTES must exceed MAX_UPLOAD_FILE_SIZE")
        if self.PORTABLE_ARCHIVE_REQUEST_BODY_MAX_BYTES <= self.PORTABLE_ARCHIVE_MAX_BYTES:
            raise ValueError(
                "PORTABLE_ARCHIVE_REQUEST_BODY_MAX_BYTES must exceed PORTABLE_ARCHIVE_MAX_BYTES"
            )
        if self.RESUME_PHOTO_EDGE_PX**2 > self.RESUME_PHOTO_MAX_PIXELS:
            raise ValueError("RESUME_PHOTO_EDGE_PX must fit inside RESUME_PHOTO_MAX_PIXELS")
        if self.PORTABLE_ARCHIVE_MAX_UNCOMPRESSED_BYTES < self.PORTABLE_ARCHIVE_MAX_BYTES:
            raise ValueError(
                "PORTABLE_ARCHIVE_MAX_UNCOMPRESSED_BYTES must cover PORTABLE_ARCHIVE_MAX_BYTES"
            )
        for field_name in (
            "LLM_PLAN_MODEL",
            "LLM_MATCH_MODEL",
            "LLM_NORMALIZE_MODEL",
            "LLM_NORMALIZE_PROFILE_MODEL",
            "LLM_COMPRESS_MODEL",
            "LLM_CRITIQUE_MODEL",
            "LLM_RERANK_MODEL",
        ):
            override = str(getattr(self, field_name, "") or "").strip()
            if override and override != self.LOCAL_MODEL:
                raise ValueError(
                    f"{field_name} must be empty or match LOCAL_MODEL so readiness attests "
                    "the model used by every analysis step"
                )
        if self.ENVIRONMENT == "production":
            secret = self.SECRET_KEY
            if (
                len(secret) < 32
                or secret != secret.strip()
                or any(ord(character) < 32 or ord(character) == 127 for character in secret)
                or secret in {"changeme", "local-development-only"}
            ):
                raise ValueError(
                    "Set a private SECRET_KEY of at least 32 characters for production"
                )
        if not 1 <= self.SQLITE_BUSY_TIMEOUT_MS <= 300_000:
            raise ValueError("SQLITE_BUSY_TIMEOUT_MS must be between 1 and 300000")
        return self


settings = Settings()
