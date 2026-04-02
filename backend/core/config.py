import logging
from typing import Any, List, Optional

from pydantic import ValidationInfo, field_validator
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
    # Optional effective context-window hint used by adaptive batching.
    # When 0, the runtime falls back to provider.max_tokens as the best signal.
    LLM_CONTEXT_WINDOW: int = 0
    # Default model: moonshotai/kimi-k2-instruct-0905 is available on Groq and offers
    # strong reasoning at a low cost. Override via LLM_MODEL env var.
    LLM_MODEL: str = "moonshotai/kimi-k2-instruct-0905"
    LLM_MAX_TOKENS: int = 16384
    LLM_TEMPERATURE: float = 0.7
    LLM_TOP_P: float = 0.95
    LLM_THINKING: bool = False
    LLM_THINKING_LEVEL: str = "OFF"

    # ─── GPT4Free / g4f ───────────────────────────────────────────────────────
    # Leave G4F_MODEL empty to let g4f auto-select the best available model.
    G4F_MODEL: str = ""
    # Comma-separated provider list used to build a RetryProvider chain.
    # Example: "HuggingChat,DeepInfra,Blackbox"
    G4F_PROVIDERS: str = ""
    # Optional override for HAR / cookie auth files. Empty = use repository default.
    G4F_COOKIES_DIR: str = ""
    G4F_PROXY: str = ""
    G4F_SHUFFLE_PROVIDERS: bool = True
    # Number of retry attempts for each low-level g4f request.
    G4F_MAX_REQUEST_ATTEMPTS: int = 2
    # Hard cap for a single low-level g4f request attempt. Prevents a single provider call
    # from consuming an entire step budget when the upstream endpoint stalls.
    G4F_REQUEST_TIMEOUT_CAP_SECONDS: float = 20.0
    # Reserve a small amount of wall-clock time so we can bail out cleanly before the
    # step-level timeout is exhausted.
    G4F_TIMEOUT_BUFFER_SECONDS: float = 1.0
    # How long (seconds) to wait before retrying after a rate-limit error (e.g. 100 req/hour).
    # Default 3600 = wait for the provider's hourly window to reset then continue.
    G4F_RATE_LIMIT_WAIT_SECONDS: float = 3600.0
    # When enabled and G4F_PROVIDERS is empty, g4f tries to discover a usable provider chain.
    G4F_AUTO_DISCOVER_PROVIDERS: bool = True
    # When disabled, an empty or broken provider chain raises explicitly instead of delegating
    # to g4f's opaque internal provider selection.
    G4F_ALLOW_INTERNAL_PROVIDER_FALLBACK: bool = False

    # ─── Secondary LLM failover ──────────────────────────────────────────────
    # Used when the primary g4f provider cannot initialize or serve a request.
    LLM_FALLBACK_PROVIDER: str = ""
    LLM_FALLBACK_API_KEY: str = ""
    LLM_FALLBACK_BASE_URL: str = ""
    LLM_FALLBACK_MODEL: str = ""
    LLM_FALLBACK_MAX_TOKENS: Optional[int] = None
    LLM_FALLBACK_TEMPERATURE: Optional[float] = None
    LLM_FALLBACK_TOP_P: Optional[float] = None
    LLM_FALLBACK_THINKING: Optional[bool] = None
    LLM_FALLBACK_THINKING_LEVEL: str = ""

    # ─── Per-step LLM overrides (all optional — empty/zero = use global) ───────
    #
    # Step: PLAN  (generate_search_plan)
    LLM_PLAN_PROVIDER: str = ""
    LLM_PLAN_MODEL: str = ""
    LLM_PLAN_API_KEY: str = ""
    LLM_PLAN_BASE_URL: str = ""
    LLM_PLAN_CONTEXT_WINDOW: int = 0
    LLM_PLAN_TEMPERATURE: Optional[float] = None
    LLM_PLAN_TOP_P: Optional[float] = None
    LLM_PLAN_MAX_TOKENS: Optional[int] = None
    LLM_PLAN_THINKING: Optional[bool] = None
    LLM_PLAN_THINKING_LEVEL: str = ""

    # Step: MATCH  (analyze_job_match)
    LLM_MATCH_PROVIDER: str = ""
    LLM_MATCH_MODEL: str = ""
    LLM_MATCH_API_KEY: str = ""
    LLM_MATCH_BASE_URL: str = ""
    LLM_MATCH_CONTEXT_WINDOW: int = 0
    LLM_MATCH_TEMPERATURE: Optional[float] = None
    LLM_MATCH_TOP_P: Optional[float] = None
    LLM_MATCH_MAX_TOKENS: Optional[int] = None
    LLM_MATCH_THINKING: Optional[bool] = None
    LLM_MATCH_THINKING_LEVEL: str = ""

    # Step: NORMALIZE  (normalize_job_batch)
    LLM_NORMALIZE_PROVIDER: str = ""
    LLM_NORMALIZE_MODEL: str = ""
    LLM_NORMALIZE_API_KEY: str = ""
    LLM_NORMALIZE_BASE_URL: str = ""
    LLM_NORMALIZE_CONTEXT_WINDOW: int = 0
    LLM_NORMALIZE_TEMPERATURE: Optional[float] = None
    LLM_NORMALIZE_TOP_P: Optional[float] = None
    LLM_NORMALIZE_MAX_TOKENS: Optional[int] = None
    LLM_NORMALIZE_THINKING: Optional[bool] = None
    LLM_NORMALIZE_THINKING_LEVEL: str = ""

    # Step: NORMALIZE_PROFILE  (normalize_user_profile — extract structured candidate data from CV + role_description)
    LLM_NORMALIZE_PROFILE_PROVIDER: str = ""
    LLM_NORMALIZE_PROFILE_MODEL: str = ""
    LLM_NORMALIZE_PROFILE_API_KEY: str = ""
    LLM_NORMALIZE_PROFILE_BASE_URL: str = ""
    LLM_NORMALIZE_PROFILE_CONTEXT_WINDOW: int = 0
    LLM_NORMALIZE_PROFILE_TEMPERATURE: Optional[float] = None
    LLM_NORMALIZE_PROFILE_TOP_P: Optional[float] = None
    LLM_NORMALIZE_PROFILE_MAX_TOKENS: Optional[int] = None
    LLM_NORMALIZE_PROFILE_THINKING: Optional[bool] = None
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
    ANALYSIS_CONCURRENCY: int = 5
    ANALYSIS_BATCH_SIZE: int = 5
    # Soft prompt-size target for MATCH batches. The final prompt also includes
    # long instructions and profile context, so keep this conservative.
    MATCH_PROMPT_TARGET_CHARS: int = 7000
    # Max chars of compacted job description evidence sent per job in MATCH.
    MATCH_PROMPT_JOB_MAX_DESCRIPTION_CHARS: int = 1800
    # Jobs per normalization LLM prompt. Smaller = fewer context-limit errors.
    NORMALIZE_BATCH_SIZE: int = 10
    # Soft prompt-size target for NORMALIZE batches.
    NORMALIZE_PROMPT_TARGET_CHARS: int = 9000
    # Max chars of compacted job description evidence sent per job in NORMALIZE.
    NORMALIZE_PROMPT_JOB_MAX_DESCRIPTION_CHARS: int = 2400
    # Max number of high-signal fragments preserved when compacting long job text.
    PROMPT_COMPACTION_MAX_FRAGMENTS: int = 12
    # Persisted deterministic compact excerpt reused across NORMALIZE and MATCH.
    SEARCH_COMPACT_DESCRIPTION_CACHE_MAX_CHARS: int = 1400
    # Persisted deterministic compact profile snapshot reused by MATCH.
    SEARCH_PROFILE_SNAPSHOT_MAX_CHARS: int = 1000

    # Low-context execution policy for small-window models.
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

    # Adecco source tuning
    ADECCO_DETAIL_CONCURRENCY: int = 4

    # Pipeline & LLM call timeouts
    # Total allowed wall-clock time for a single end-to-end search run (seconds).
    SEARCH_PIPELINE_TIMEOUT_SECONDS: int = 1800  # 30 minutes
    # Maximum number of concurrent active searches allowed per user.
    MAX_CONCURRENT_SEARCHES_PER_USER: int = 3
    # Per-step LLM call timeouts (seconds).  0 = disabled.
    LLM_CALL_TIMEOUT_PLAN: int = 60
    # Optional tighter PLAN timeout budget for g4f to avoid long retry storms.
    # 0 = disabled (use LLM_CALL_TIMEOUT_PLAN).
    LLM_CALL_TIMEOUT_PLAN_G4F: int = 45
    # Number of service-level retry attempts for PLAN generation.
    LLM_PLAN_RETRY_ATTEMPTS: int = 2
    LLM_CALL_TIMEOUT_NORMALIZE: int = 90
    # Optional tighter NORMALIZE / NORMALIZE_PROFILE / COMPRESS timeout budget for g4f.
    LLM_CALL_TIMEOUT_NORMALIZE_G4F: int = 60
    LLM_CALL_TIMEOUT_MATCH: int = 120
    # Optional tighter MATCH timeout budget for g4f.
    LLM_CALL_TIMEOUT_MATCH_G4F: int = 90

    # Circuit breaker (per provider)
    # Number of consecutive failures before tripping to OPEN state.
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 10
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
    LLM_CALL_TIMEOUT_CRITIQUE_G4F: int = 60
    LLM_CALL_TIMEOUT_RERANK: int = 60
    LLM_CALL_TIMEOUT_RERANK_G4F: int = 45

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

    @field_validator("G4F_MAX_REQUEST_ATTEMPTS")
    @classmethod
    def validate_g4f_max_request_attempts(cls, value: int) -> int:
        attempts = int(value)
        if attempts < 1:
            logger.warning("G4F_MAX_REQUEST_ATTEMPTS=%s is invalid; clamping to 1.", value)
            return 1
        return attempts

    @field_validator("LLM_PLAN_RETRY_ATTEMPTS")
    @classmethod
    def validate_plan_retry_attempts(cls, value: int) -> int:
        attempts = int(value)
        if attempts < 1:
            logger.warning("LLM_PLAN_RETRY_ATTEMPTS=%s is invalid; clamping to 1.", value)
            return 1
        return attempts

    @field_validator(
        "LLM_CALL_TIMEOUT_PLAN_G4F",
        "LLM_CALL_TIMEOUT_NORMALIZE_G4F",
        "LLM_CALL_TIMEOUT_MATCH_G4F",
        "LLM_CALL_TIMEOUT_CRITIQUE_G4F",
        "LLM_CALL_TIMEOUT_RERANK_G4F",
        mode="before",
    )
    @classmethod
    def clamp_non_negative_int_timeout(cls, value: Any, info: ValidationInfo) -> int:
        if value in (None, ""):
            return 0
        coerced = int(value)
        if coerced < 0:
            logger.warning("%s=%s is invalid; clamping to 0.", info.field_name, value)
            return 0
        return coerced

    @field_validator("G4F_REQUEST_TIMEOUT_CAP_SECONDS", "G4F_TIMEOUT_BUFFER_SECONDS")
    @classmethod
    def clamp_non_negative_float(cls, value: float, info: ValidationInfo) -> float:
        coerced = float(value)
        if coerced < 0:
            logger.warning("%s=%s is invalid; clamping to 0.", info.field_name, value)
            return 0.0
        return coerced

    def model_post_init(self, __context: Any) -> None:
        provider_name = (self.LLM_PROVIDER or "").strip().lower()
        if provider_name != "g4f":
            return

        if not (self.LLM_FALLBACK_PROVIDER or "").strip():
            logger.warning(
                "LLM_PROVIDER=g4f without LLM_FALLBACK_PROVIDER configured; g4f outages will fail the pipeline instead of failing over."
            )

        if not (self.G4F_PROVIDERS or "").strip() and self.G4F_ALLOW_INTERNAL_PROVIDER_FALLBACK:
            logger.warning(
                "G4F_PROVIDERS is empty while G4F_ALLOW_INTERNAL_PROVIDER_FALLBACK=true; runtime provider selection will be opaque and less deterministic."
            )

        if self.LLM_THINKING:
            logger.warning("LLM_THINKING is enabled but g4f providers ignore thinking mode.")

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env", extra="ignore")


settings = Settings()
