import logging
from typing import Any, List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Job Hunter AI"

    # CORS
    CORS_ORIGINS: Optional[str] = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"
    )
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
                if self.ENVIRONMENT == "production":
                    raise ValueError(
                        f"Invalid CORS_ORIGINS JSON in production environment: {exc}"
                    ) from exc
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
        import logging
        import os

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
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # 7 days
    # ─── Global LLM (used as fallback for all steps) ───────────────────────────
    LLM_PROVIDER: str = "groq"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    # Default model: moonshotai/kimi-k2-instruct-0905 is available on Groq and offers
    # strong reasoning at a low cost. Override via LLM_MODEL env var.
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
    LLM_PLAN_TEMPERATURE: Optional[float] = None
    LLM_PLAN_TOP_P: Optional[float] = None
    LLM_PLAN_MAX_TOKENS: Optional[int] = None
    LLM_PLAN_THINKING: bool = False
    LLM_PLAN_THINKING_LEVEL: str = ""

    # Step: MATCH  (analyze_job_match)
    LLM_MATCH_PROVIDER: str = ""
    LLM_MATCH_MODEL: str = ""
    LLM_MATCH_API_KEY: str = ""
    LLM_MATCH_BASE_URL: str = ""
    LLM_MATCH_TEMPERATURE: Optional[float] = None
    LLM_MATCH_TOP_P: Optional[float] = None
    LLM_MATCH_MAX_TOKENS: Optional[int] = None
    LLM_MATCH_THINKING: bool = False
    LLM_MATCH_THINKING_LEVEL: str = ""

    # Step: NORMALIZE  (normalize_job_batch)
    LLM_NORMALIZE_PROVIDER: str = ""
    LLM_NORMALIZE_MODEL: str = ""
    LLM_NORMALIZE_API_KEY: str = ""
    LLM_NORMALIZE_BASE_URL: str = ""
    LLM_NORMALIZE_TEMPERATURE: Optional[float] = None
    LLM_NORMALIZE_TOP_P: Optional[float] = None
    LLM_NORMALIZE_MAX_TOKENS: Optional[int] = None
    LLM_NORMALIZE_THINKING: bool = False
    LLM_NORMALIZE_THINKING_LEVEL: str = ""

    # Step: NORMALIZE_PROFILE  (normalize_user_profile — extract structured candidate data from CV + role_description)
    LLM_NORMALIZE_PROFILE_PROVIDER: str = ""
    LLM_NORMALIZE_PROFILE_MODEL: str = ""
    LLM_NORMALIZE_PROFILE_API_KEY: str = ""
    LLM_NORMALIZE_PROFILE_BASE_URL: str = ""
    LLM_NORMALIZE_PROFILE_TEMPERATURE: Optional[float] = None
    LLM_NORMALIZE_PROFILE_TOP_P: Optional[float] = None
    LLM_NORMALIZE_PROFILE_MAX_TOKENS: Optional[int] = None
    LLM_NORMALIZE_PROFILE_THINKING: bool = False
    LLM_NORMALIZE_PROFILE_THINKING_LEVEL: str = ""

    # Scraping
    JOB_ROOM_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

    # File uploads
    MAX_UPLOAD_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB

    # Analysis Pipeline Tuning
    MAX_DESCRIPTION_CHARS: int = 64000
    SEARCH_EXECUTION_MODE: str = "sequential"
    SEARCH_CONCURRENCY: int = 3
    SEARCH_PLAN_ENABLE_LOOSE_DEDUP: bool = True
    SEARCH_ENABLE_DEGRADED_PLAN_FALLBACK: bool = True
    SEARCH_DEGRADED_PLAN_MAX_QUERIES: int = 3
    SEARCH_DEGRADED_PLAN_MAX_KEYWORDS: int = 2
    ANALYSIS_CONCURRENCY: int = 15
    ANALYSIS_BATCH_SIZE: int = 5
    # Jobs per normalization LLM prompt. Smaller = fewer context-limit errors.
    NORMALIZE_BATCH_SIZE: int = 10

    # Pipeline & LLM call timeouts
    # Total allowed wall-clock time for a single end-to-end search run (seconds).
    SEARCH_PIPELINE_TIMEOUT_SECONDS: int = 1800  # 30 minutes
    # Per-step LLM call timeouts (seconds).  0 = disabled.
    LLM_CALL_TIMEOUT_PLAN: int = 60
    LLM_CALL_TIMEOUT_NORMALIZE: int = 90
    LLM_CALL_TIMEOUT_MATCH: int = 120

    # Circuit breaker (per provider)
    # Number of consecutive failures before tripping to OPEN state.
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    # Seconds to wait in OPEN state before trying a probe call (HALF_OPEN).
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 60

    # Normalization-based profile matching (Phase 2)
    # When enabled, structured filters compare normalized user profile fields
    # (seniority, domain, qualification, experience) against normalized job fields,
    # providing a deterministic pre-screen before the expensive LLM analysis step.
    SEARCH_ENABLE_NORMALIZATION_MATCHING: bool = True
    # Tolerance in years added to user experience for experience-floor matching.
    # E.g. user has 3 yrs → jobs requiring up to 3+2=5 yrs min still pass.
    SEARCH_NORMALIZATION_EXPERIENCE_TOLERANCE: int = 3

    # ─── Normalization quality & confidence-tiered re-normalization ───────────
    # When enabled, low-confidence jobs get a second targeted normalization pass.
    NORMALIZATION_RENORMALIZE_ENABLED: bool = True
    # Jobs with confidence >= TIER1 are accepted as-is.
    NORMALIZATION_CONFIDENCE_TIER1_THRESHOLD: float = 0.70
    # Jobs with confidence >= TIER2 (and < TIER1) are accepted but flagged.
    # Jobs below TIER2 get a second-pass re-normalization call.
    NORMALIZATION_CONFIDENCE_TIER2_THRESHOLD: float = 0.40

    # ─── Structured pre-score gate (runs before expensive MATCH step) ─────────
    # When enabled, jobs must reach STRUCTURED_PRESCORE_THRESHOLD to pass to MATCH.
    STRUCTURED_PRESCORE_ENABLED: bool = True
    # Minimum composite pre-score (0–100) required to pass to the MATCH step.
    # Raised from 20 → 30 to reduce token waste on weak matches.
    STRUCTURED_PRESCORE_THRESHOLD: float = 30.0
    # Stricter threshold applied once the user has accumulated preference signals
    # (>= PREFERENCE_MIN_SIGNAL_COUNT interactions).  The system can afford to be
    # pickier when it knows the user's patterns.
    STRUCTURED_PRESCORE_THRESHOLD_WITH_PREFS: float = 35.0

    # ─── MATCH quality improvements ───────────────────────────────────────────
    # Evidence-grounded MATCH: prompt requires citing specific text from job description.
    MATCH_EVIDENCE_GROUNDED: bool = True
    # Two-pass critique: re-analyze borderline jobs (45–80 score range).
    MATCH_CRITIQUE_ENABLED: bool = True
    MATCH_CRITIQUE_SCORE_RANGE_MIN: int = 40
    MATCH_CRITIQUE_SCORE_RANGE_MAX: int = 80
    # Comparative re-ranking of the top-N jobs after individual scoring.
    MATCH_RERANK_ENABLED: bool = True
    MATCH_RERANK_TOP_N: int = 20

    # ─── Job intelligence ─────────────────────────────────────────────────────
    # Detect and store red flags in job descriptions.
    RED_FLAGS_DETECTION_ENABLED: bool = True
    # Apply posting publication-date decay to final scores.
    RECENCY_WEIGHTING_ENABLED: bool = True
    # Number of days after which a job starts losing score due to age.
    RECENCY_DECAY_HALFLIFE_DAYS: int = 30

    # ─── Per-step LLM overrides: CRITIQUE step ────────────────────────────────
    LLM_CRITIQUE_PROVIDER: str = ""
    LLM_CRITIQUE_MODEL: str = ""
    LLM_CRITIQUE_API_KEY: str = ""
    LLM_CRITIQUE_BASE_URL: str = ""
    LLM_CRITIQUE_TEMPERATURE: Optional[float] = None
    LLM_CRITIQUE_TOP_P: Optional[float] = None
    LLM_CRITIQUE_MAX_TOKENS: Optional[int] = None

    # ─── Per-step LLM overrides: RERANK step ─────────────────────────────────
    LLM_RERANK_PROVIDER: str = ""
    LLM_RERANK_MODEL: str = ""
    LLM_RERANK_API_KEY: str = ""
    LLM_RERANK_BASE_URL: str = ""
    LLM_RERANK_TEMPERATURE: Optional[float] = None
    LLM_RERANK_TOP_P: Optional[float] = None
    LLM_RERANK_MAX_TOKENS: Optional[int] = None

    # ─── Per-step timeouts: new steps ─────────────────────────────────────────
    LLM_CALL_TIMEOUT_CRITIQUE: int = 90
    LLM_CALL_TIMEOUT_RERANK: int = 60

    # ─── Semantic Skill Matching (Phase 1 — embedding-based) ────────────────────
    # Enable embedding-based Tier 2.5 in semantic_skills_score().
    # Requires sentence-transformers to be installed.
    SKILL_EMBEDDING_ENABLED: bool = True
    # Cosine similarity threshold: pairs below this are ignored by the embedding tier.
    SKILL_EMBEDDING_THRESHOLD: float = 0.65
    # HuggingFace model name. Must be a sentence-transformers compatible model.
    # Default: all-MiniLM-L6-v2 (22MB, multilingual, runs locally, no API cost).
    SKILL_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # ─── User Feedback & Personalisation (Phase 2) ────────────────────────────
    # Inject user behavioural signals into the MATCH LLM prompt when enough data.
    MATCH_ENABLE_PREFERENCE_INJECTION: bool = True
    # Minimum number of jobs with signals (applied/dismissed) before activating.
    PREFERENCE_MIN_SIGNAL_COUNT: int = 10
    # Enable preference-based pre-score component.
    PREFERENCE_PRESCORE_ENABLED: bool = True

    # Progressive dealbreaker escalation — dismissal thresholds for each tier.
    # Tier 1 (3+ dismissals same signal): prescore penalty −3 pts
    # Tier 2 (6+ dismissals same signal): prescore penalty −5 pts
    # Tier 3 (10+ dismissals same signal): prescore penalty −8 pts + hard filter in structured gating
    DEALBREAKER_ESCALATION_TIER1: int = 3
    DEALBREAKER_ESCALATION_TIER2: int = 6
    DEALBREAKER_ESCALATION_TIER3: int = 10

    # ─── Swiss Market Enhancements (Phase 3) ──────────────────────────────────
    # Inject implicit language requirements (canton-based) into MATCH prompt.
    SWISS_IMPLICIT_LANGUAGE_ENABLED: bool = True
    # Add salary_below_market red flag based on aggregated ScrapedJob salary data.
    SALARY_BENCHMARK_ENABLED: bool = True

    # Logging
    LOG_LEVEL: str = "INFO"

    # Ollama Defaults
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "llama3"

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env", extra="ignore")


settings = Settings()
