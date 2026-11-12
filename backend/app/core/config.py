from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # Application
    APP_ENV: str = "development"
    APP_NAME: str = "VinUni HRA API"
    API_V1_PREFIX: str = "/v1"
    DEBUG: bool = False

    # Database - direct PostgreSQL connection string
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/hra"
    DATABASE_POOL_SIZE: int = 5

    # Supabase (optional - used for Auth and Storage if provided)
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    # Legacy HS256 verification only. Projects using asymmetric signing keys
    # (for example ES256) are verified through JWKS derived from SUPABASE_URL.
    SUPABASE_JWT_SECRET: str = ""
    SUPABASE_JWT_ISSUER: Optional[str] = None
    SUPABASE_JWKS_URL: Optional[str] = None
    SUPABASE_JWKS_CACHE_SECONDS: int = 300

    # Disabled by default. Set a unique random token only during first-admin
    # setup, over HTTPS and a restricted network; remove it afterwards.
    ADMIN_BOOTSTRAP_TOKEN: str = ""

    # Storage (local or Supabase)
    STORAGE_BACKEND: str = "local"  # "local" or "supabase"
    LOCAL_STORAGE_PATH: str = "./storage"
    SUPABASE_STORAGE_BUCKET_CV: str = "cv-originals"
    SUPABASE_STORAGE_BUCKET_EXTRACTED: str = "cv-extracted-text"

    # File upload limits
    MAX_FILE_SIZE_BYTES: int = 10_000_000  # 10 MB
    MAX_FILES_PER_BATCH: int = 50
    MAX_BATCH_SIZE_BYTES: int = 250_000_000  # 250 MB

    # AI/LLM
    LLM_PROVIDER: str = "local"  # local/openai/azure/compatible labels; same OpenAI-compatible transport
    LLM_PROVIDER_NAME: Optional[str] = None
    LLM_MODEL_NAME: str = "vinuni/hra-llm-7b"
    LLM_API_BASE: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    # Server-only Fernet key used to encrypt API keys entered by an Admin for
    # an OpenAI-compatible provider. Generate one with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Rotating it makes previously stored provider keys undecryptable.
    AI_CONFIG_ENCRYPTION_KEY: str = ""
    # Optional JSON arrays. The environment default endpoint/model are always
    # included. These are operator policy, never editable in the UI.
    LLM_ALLOWED_API_BASES: list[str] = []
    LLM_ALLOWED_MODELS: list[str] = []
    LLM_TEMPERATURE_DEFAULT: float = 0.1
    # Optional provider seed. Leave unset unless the selected OpenAI-compatible
    # provider explicitly supports `seed`; determinism is still best-effort.
    LLM_SEED: int | None = None
    ALLOW_EXTERNAL_API: bool = False
    # Opt-in provider-enforced JSON Schema for matching. Some compatible
    # endpoints reject this response format, so it stays off by default and
    # client-side validation remains the fallback.
    LLM_STRICT_JSON_SCHEMA: bool = False

    # Matching/Scoring. Bump these versions whenever prompt, scoring or rule
    # behaviour changes; assessment fingerprints include them so old results
    # are never silently mixed with new behaviour.
    ASSESSMENT_POLICY_VERSION: str = "assessment-v2.0"
    MATCHING_POLICY_VERSION: str = "matching-v2.1"
    RANKING_POLICY_VERSION: str = "ranking-v2.0"
    CRITERIA_PROMPT_VERSION: str = "criteria-prompt-v2.1"
    PROFILE_PROMPT_VERSION: str = "profile-prompt-v2.0"
    MATCHING_PROMPT_VERSION: str = "matching-prompt-v2.0"
    DETERMINISTIC_RULES_VERSION: str = "deterministic-rules-v1.4"
    MANDATORY_CRITERIA_WEIGHT_DEFAULT: float = 0.7
    NICE_TO_HAVE_WEIGHT_DEFAULT: float = 0.3
    MIN_EVIDENCE_COVERAGE: float = 0.7
    STRONG_MATCH_SCORE: int = 100
    MATCH_SCORE: int = 80
    NO_MATCH_SCORE: int = 0

    # Legacy compatibility settings, NOT worker activation controls after 00019.
    # Managed BGE is OFF by default in ai_runtime_controls and is pinned per job.
    SEMANTIC_RETRIEVAL_ENABLED: bool = False
    # Legacy only: managed worker activation is controlled by the database.
    ALLOW_MANAGED_BGE_ROUTING: bool = False
    EMBEDDING_PROVIDER: str = "disabled"  # disabled | bge_http | hash
    EMBEDDING_API_BASE: str | None = None
    EMBEDDING_API_KEY: str | None = None
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIMENSION: int = 1024
    EMBEDDING_INDEX_VERSION: str = "bge-index-v1"
    EMBEDDING_TIMEOUT_SECONDS: float = 30.0
    EMBEDDING_QUERY_INSTRUCTION: str = ""
    SEMANTIC_TOP_K: int = 5
    SEMANTIC_MIN_SIMILARITY: float = 0.35

    # Learning-to-Rank. OFF by default; SHADOW scores without changing the
    # published order, ACTIVE may reorder only inside the existing
    # mandatory-status/coverage gates when a gated model artifact is loaded.
    # Legacy flags/model paths are not worker activation controls after 00019;
    # managed selections in the database are authoritative.
    ALLOW_MANAGED_LTR_ROUTING: bool = False
    LTR_MODE: str = "OFF"  # OFF | SHADOW | ACTIVE
    LTR_MODEL_PATH: str | None = None
    LTR_MODEL_VERSION: str | None = None
    LTR_MIN_NDCG_AT_10: float = 0.70
    LTR_MIN_PAIRWISE_ACCURACY: float = 0.65
    LTR_MIN_HOLDOUT_EXAMPLES: int = 20
    LTR_MIN_HOLDOUT_GROUPS: int = 2

    # Langfuse AI observability. Disabled by default and metadata-first:
    # enabling it must never be required for LLM, worker or assessment
    # operations. Content capture is additionally blocked in production by
    # app.services.langfuse_observability.
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: Optional[str] = None
    LANGFUSE_BASE_URL: Optional[str] = None
    LANGFUSE_ENVIRONMENT: Optional[str] = None
    LANGFUSE_RELEASE: Optional[str] = None
    LANGFUSE_SAMPLE_RATE: float = 1.0
    LANGFUSE_CAPTURE_CONTENT: bool = False

    # Retention
    RETENTION_MONTHS: int = 12

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Security
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours


settings = Settings()
