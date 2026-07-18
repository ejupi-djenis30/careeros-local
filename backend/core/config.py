import json
import logging
import os
from pathlib import Path
from typing import Any, List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.inference.endpoint import validate_local_inference_url

logger = logging.getLogger(__name__)


def _local_secret_default() -> str:
    """Load the installation secret for zero-config local container commands."""
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    secret_path = Path(os.environ.get("CAREEROS_SECRET_FILE", data_dir / ".secret-key"))
    try:
        value = secret_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "local-development-only"
    return value if len(value) >= 32 else "local-development-only"


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

    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "CareerOS Local"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    OFFLINE_MODE: bool = False

    CORS_ORIGINS: Optional[str] = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"
    )
    CORS_ALLOW_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1", "testserver"]

    DATABASE_URL: str = "sqlite:///./data/careeros.db"
    DATA_DIR: str = "data"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    SQLITE_BUSY_TIMEOUT_MS: int = 5000

    SECRET_KEY: str = Field(default_factory=_local_secret_default)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # The only supported inference runtime is a host explicitly considered local.
    LOCAL_INFERENCE_ALLOWED_HOSTS: str = (
        "localhost,127.0.0.1,::1,ollama,host.docker.internal"
    )
    LOCAL_INFERENCE_URL: str = "http://127.0.0.1:11434"
    LOCAL_MODEL: str = "qwen3:1.7b"
    LOCAL_INFERENCE_CONNECT_TIMEOUT_SECONDS: float = 2.0
    LOCAL_INFERENCE_REQUEST_TIMEOUT_SECONDS: float = 180.0

    # Local model tuning. Per-step model fields are optional and fall back to LOCAL_MODEL.
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
    LLM_CALL_TIMEOUT_CRITIQUE: int = 90
    LLM_CALL_TIMEOUT_RERANK: int = 60
    LLM_PLAN_RETRY_ATTEMPTS: int = 2
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 30

    JOB_ROOM_USER_AGENT: str = "CareerOS-Local/2.0"
    MAX_UPLOAD_FILE_SIZE: int = 10 * 1024 * 1024
    RESUME_MAX_PAGES: int = 3
    RESUME_PHOTO_MAX_PIXELS: int = 25_000_000
    RESUME_PHOTO_EDGE_PX: int = 720
    PORTABLE_ARCHIVE_MAX_BYTES: int = 512 * 1024 * 1024
    PORTABLE_ARCHIVE_MAX_UNCOMPRESSED_BYTES: int = 1024 * 1024 * 1024
    PORTABLE_ARCHIVE_MAX_MEMBERS: int = 20_000
    PORTABLE_ARCHIVE_MAX_RECORDS: int = 250_000
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
        if not self.CORS_ORIGINS:
            return []
        if self.CORS_ORIGINS.startswith("["):
            try:
                value = json.loads(self.CORS_ORIGINS)
                return [str(item).strip() for item in value if str(item).strip()]
            except Exception as exc:
                if self.ENVIRONMENT.lower() == "production":
                    raise ValueError(f"Invalid CORS_ORIGINS JSON: {exc}") from exc
                logger.warning("Invalid CORS_ORIGINS JSON %r: %s", self.CORS_ORIGINS, exc)
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

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
        if not isinstance(value, str):
            return value
        if value.startswith("["):
            try:
                return json.loads(value)
            except Exception as exc:
                logger.warning("Invalid ALLOWED_HOSTS JSON %r: %s", value, exc)
        return [item.strip() for item in value.split(",") if item.strip()]

    @model_validator(mode="after")
    def validate_local_first_settings(self) -> "Settings":
        self.LOCAL_INFERENCE_URL = validate_local_inference_url(
            self.LOCAL_INFERENCE_URL,
            allowed_hosts=self.local_inference_allowed_hosts,
        )
        if self.ENVIRONMENT.lower() == "production" and self.SECRET_KEY in {
            "",
            "changeme",
            "local-development-only",
        }:
            raise ValueError("Set a private SECRET_KEY for production")
        if self.SQLITE_BUSY_TIMEOUT_MS < 0:
            raise ValueError("SQLITE_BUSY_TIMEOUT_MS must be non-negative")
        return self


settings = Settings()
