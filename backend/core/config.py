from typing import List, Union, Any, Optional
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Job Hunter AI"
    
    # CORS
    CORS_ORIGINS: Optional[str] = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"

    @property
    def cors_origins_list(self) -> List[str]:
        if not self.CORS_ORIGINS:
            return []
        if self.CORS_ORIGINS.startswith("["):
            import json
            try:
                return json.loads(self.CORS_ORIGINS)
            except Exception:
                pass
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
                except Exception:
                    pass
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
    LLM_PLAN_TEMPERATURE: float = 0.0
    LLM_PLAN_TOP_P: float = 0.0
    LLM_PLAN_MAX_TOKENS: int = 0
    LLM_PLAN_THINKING: bool = False
    LLM_PLAN_THINKING_LEVEL: str = ""

    # Step: RELEVANCE  (check_title_relevance)
    LLM_RELEVANCE_PROVIDER: str = ""
    LLM_RELEVANCE_MODEL: str = ""
    LLM_RELEVANCE_API_KEY: str = ""
    LLM_RELEVANCE_BASE_URL: str = ""
    LLM_RELEVANCE_TEMPERATURE: float = 0.0
    LLM_RELEVANCE_TOP_P: float = 0.0
    LLM_RELEVANCE_MAX_TOKENS: int = 0
    LLM_RELEVANCE_THINKING: bool = False
    LLM_RELEVANCE_THINKING_LEVEL: str = ""

    # Step: MATCH  (analyze_job_match)
    LLM_MATCH_PROVIDER: str = ""
    LLM_MATCH_MODEL: str = ""
    LLM_MATCH_API_KEY: str = ""
    LLM_MATCH_BASE_URL: str = ""
    LLM_MATCH_TEMPERATURE: float = 0.0
    LLM_MATCH_TOP_P: float = 0.0
    LLM_MATCH_MAX_TOKENS: int = 0
    LLM_MATCH_THINKING: bool = False
    LLM_MATCH_THINKING_LEVEL: str = ""

    # Step: SUMMARY  (summarize_job_batch — opt-in, only active when configured)
    LLM_SUMMARY_PROVIDER: str = ""
    LLM_SUMMARY_MODEL: str = ""
    LLM_SUMMARY_API_KEY: str = ""
    LLM_SUMMARY_BASE_URL: str = ""
    LLM_SUMMARY_TEMPERATURE: float = 0.0
    LLM_SUMMARY_TOP_P: float = 0.0
    LLM_SUMMARY_MAX_TOKENS: int = 0
    LLM_SUMMARY_THINKING: bool = False
    LLM_SUMMARY_THINKING_LEVEL: str = ""

    # Scraping
    JOB_ROOM_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

    # Analysis Pipeline Tuning
    MAX_DESCRIPTION_CHARS: int = 6000
    SEARCH_CONCURRENCY: int = 3
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
