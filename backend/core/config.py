import logging
from typing import List, Union, Any, Optional
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Job Hunter AI"
    
    # CORS
    CORS_ORIGINS: Optional[str] = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"
    CORS_ALLOW_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    @property
    def cors_origins_list(self) -> List[str]:
        if not self.CORS_ORIGINS:
            return []
        if self.CORS_ORIGINS.startswith("["):
            import json
            try:
                return json.loads(self.CORS_ORIGINS)
            except Exception as exc:
                logger.warning("Invalid CORS_ORIGINS JSON %r: %s", self.CORS_ORIGINS, exc)
        return [i.strip() for i in self.CORS_ORIGINS.split(",") if i.strip()]

    # Database
    DATABASE_URL: str = "sqlite:///./job_hunter.db"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    
    # Security
    SECRET_KEY: str = "changeme"
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1", "testserver"]

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            if v.startswith("["):
                import json
                try:
                    return json.loads(v)
                except Exception as exc:
                    logger.warning("Invalid ALLOWED_HOSTS JSON %r: %s", v, exc)
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    ENVIRONMENT: str = "development"  # development | production

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        import os, logging
        if v in ("changeme", ""):
            if os.getenv("ENVIRONMENT", "development").lower() == "production":
                raise ValueError(
                    "Insecure default SECRET_KEY in use. Set SECRET_KEY in your environment."
                )
            logging.critical(
                "CRITICAL: Default SECRET_KEY is in use! Set SECRET_KEY in .env for production."
            )
        return v
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # 15 minutes
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7     # 7 days
    # ─── Global LLM (used as fallback for all steps) ───────────────────────────
    LLM_PROVIDER: str = "groq"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = "moonshotai/kimi-k2-instruct-0905"
    LLM_MAX_TOKENS: int = 16384
    LLM_TEMPERATURE: float = 0.7
    LLM_TOP_P: float = 0.95
    LLM_THINKING: bool = False
    LLM_THINKING_LEVEL: str = "OFF"

    # ─── Per-step LLM overrides (all optional — empty/zero = use global) ───────
    #
    # Step: PLAN  (generate_search_plan)
    LLM_PLAN_PROVIDER: str = ""
    LLM_PLAN_MODEL: str = ""
    LLM_PLAN_API_KEY: str = ""
    LLM_PLAN_BASE_URL: str = ""
    LLM_PLAN_TEMPERATURE: float = -1.0
    LLM_PLAN_TOP_P: float = -1.0
    LLM_PLAN_MAX_TOKENS: int = -1
    LLM_PLAN_THINKING: bool = False
    LLM_PLAN_THINKING_LEVEL: str = ""

    # Step: RELEVANCE  (check_title_relevance)
    LLM_RELEVANCE_PROVIDER: str = ""
    LLM_RELEVANCE_MODEL: str = ""
    LLM_RELEVANCE_API_KEY: str = ""
    LLM_RELEVANCE_BASE_URL: str = ""
    LLM_RELEVANCE_TEMPERATURE: float = -1.0
    LLM_RELEVANCE_TOP_P: float = -1.0
    LLM_RELEVANCE_MAX_TOKENS: int = -1
    LLM_RELEVANCE_THINKING: bool = False
    LLM_RELEVANCE_THINKING_LEVEL: str = ""

    # Step: MATCH  (analyze_job_match)
    LLM_MATCH_PROVIDER: str = ""
    LLM_MATCH_MODEL: str = ""
    LLM_MATCH_API_KEY: str = ""
    LLM_MATCH_BASE_URL: str = ""
    LLM_MATCH_TEMPERATURE: float = -1.0
    LLM_MATCH_TOP_P: float = -1.0
    LLM_MATCH_MAX_TOKENS: int = -1
    LLM_MATCH_THINKING: bool = False
    LLM_MATCH_THINKING_LEVEL: str = ""

    # Step: SUMMARY  (summarize_job_batch — opt-in, only active when configured)
    LLM_SUMMARY_PROVIDER: str = ""
    LLM_SUMMARY_MODEL: str = ""
    LLM_SUMMARY_API_KEY: str = ""
    LLM_SUMMARY_BASE_URL: str = ""
    LLM_SUMMARY_TEMPERATURE: float = -1.0
    LLM_SUMMARY_TOP_P: float = -1.0
    LLM_SUMMARY_MAX_TOKENS: int = -1
    LLM_SUMMARY_THINKING: bool = False
    LLM_SUMMARY_THINKING_LEVEL: str = ""

    # Step: NORMALIZE  (normalize_job_batch)
    LLM_NORMALIZE_PROVIDER: str = ""
    LLM_NORMALIZE_MODEL: str = ""
    LLM_NORMALIZE_API_KEY: str = ""
    LLM_NORMALIZE_BASE_URL: str = ""
    LLM_NORMALIZE_TEMPERATURE: float = -1.0
    LLM_NORMALIZE_TOP_P: float = -1.0
    LLM_NORMALIZE_MAX_TOKENS: int = -1
    LLM_NORMALIZE_THINKING: bool = False
    LLM_NORMALIZE_THINKING_LEVEL: str = ""

    # Scraping
    JOB_ROOM_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

    # Analysis Pipeline Tuning
    MAX_DESCRIPTION_CHARS: int = 6000
    SEARCH_EXECUTION_MODE: str = "sequential"
    SEARCH_CONCURRENCY: int = 3
    SEARCH_PLAN_BATCH_SIZE: int = 40
    SEARCH_PLAN_ENABLE_LOOSE_DEDUP: bool = True
    SEARCH_PLAN_STALL_MAX_BATCHES: int = 2
    SEARCH_ENABLE_DEGRADED_PLAN_FALLBACK: bool = True
    SEARCH_DEGRADED_PLAN_MAX_QUERIES: int = 3
    SEARCH_DEGRADED_PLAN_MAX_KEYWORDS: int = 2
    SEARCH_RELEVANCE_FALLBACK_MODE: str = "conservative"
    ANALYSIS_CONCURRENCY: int = 15
    ANALYSIS_BATCH_SIZE: int = 5

    # Logging
    LOG_LEVEL: str = "INFO"

    # Ollama Defaults
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "llama3"

    model_config = SettingsConfigDict(
        case_sensitive=True, 
        env_file=".env", 
        extra="ignore"
    )

settings = Settings()
