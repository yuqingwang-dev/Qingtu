"""Configuration management for Qingtu backend."""
from pydantic_settings import BaseSettings
from typing import Optional, Literal
from pydantic import field_validator, Field
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/qingtu"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 3600  # 1 hour default cache TTL

    # OpenAI
    # Set OPENAI_API_KEY in .env file or environment variable
    # For portfolio/demo: Set your key once at server level, users don't need their own
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_MODEL: str = "deepseek-flash"
    LLM_PROVIDER: Literal["auto", "deepseek", "openai"] = "auto"
    LLM_TIMEOUT_SECONDS: float = Field(default=30, gt=0, le=120)
    AGENT_MAX_TURNS: int = Field(default=8, ge=1, le=20)
    AGENT_MAX_TOOL_CALLS: int = Field(default=24, ge=1, le=100)
    AGENT_MAX_TOKENS: int = Field(default=12000, ge=1, le=100000)
    AGENT_TIMEOUT_SECONDS: float = Field(default=90, gt=0, le=300)

    # RAG / Embeddings
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_API_KEY: Optional[str] = None
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    RAG_TOP_K: int = 50       # Number of semantic candidates to retrieve before optimization
    RAG_ENABLED: bool = False  # Set to True after running generate_embeddings.py
    # Document RAG is separate from legacy 1536-dimensional activity embeddings.
    KNOWLEDGE_VECTOR_ENABLED: bool = True
    KNOWLEDGE_MODEL_CACHE: str = ".cache/models"  # relative to backend/

    # Google Places API
    GOOGLE_PLACES_API_KEY: Optional[str] = None  # Set in .env
    AMAP_WEB_SERVICE_KEY: Optional[str] = None
    LIVE_POI_ENABLED: bool = True
    POI_CACHE_TTL_SECONDS: int = Field(default=3600, ge=60, le=86400)
    POI_MAX_RESULTS: int = Field(default=36, ge=3, le=45)
    POI_TIMEOUT_SECONDS: float = Field(default=8, gt=0, le=20)
    ROUTE_MAX_REQUESTS: int = Field(default=100, ge=1, le=150)
    ROUTE_CACHE_TTL_SECONDS: int = Field(default=900, ge=60, le=3600)
    ROUTE_TIMEOUT_SECONDS: float = Field(default=90, gt=0, le=180)

    # CORS
    CORS_ORIGINS: list[str] | str = ["http://localhost:3000", "http://localhost:3001"]

    @field_validator('CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS_ORIGINS from JSON string or return list as-is."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # If not JSON, split by comma
                return [origin.strip() for origin in v.split(',')]
        return v

    # Session Management (no auth)
    SESSION_SECRET_KEY: str = "dev-secret-key-change-in-production"
    SESSION_COOKIE_NAME: str = "qingtu_session"

    # JWT Authentication
    JWT_SECRET_KEY: str = "dev-jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24 * 7  # 7 days

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30  # seconds
    WS_MAX_CONNECTIONS_PER_SESSION: int = 5

    # Collaboration
    COLLAB_SESSION_TIMEOUT_MINUTES: int = 120  # 2 hours

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    RATE_LIMIT_HEAVY_ENDPOINTS: int = 10  # For expensive operations
    # Daily itinerary quota; independent from per-minute request throttling.
    # Enabled unless explicitly disabled for local development.
    GENERATION_LIMIT_ENABLED: bool = True

    # Background Jobs (Celery)
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Logging & Monitoring
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: Optional[str] = None
    ENVIRONMENT: str = "development"  # development, staging, production

    # App
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    USE_ORTOOLS: bool = True  # Use OR-Tools optimizer (set to False to use greedy)

    # TripPilot Phase 1.1 — Provider contracts (non-breaking, default off).
    # When False, the new SearchProvider adapter is not wired into any runtime
    # path; existing places_service keeps being called directly by v1 code.
    USE_PROVIDER_ADAPTER: bool = False
    PROVIDER_CACHE_TTL_SECONDS: int = 3600  # short-lived provider snapshot TTL

    @field_validator(
        "DEBUG", "RAG_ENABLED", "USE_ORTOOLS", "RATE_LIMIT_ENABLED",
        "USE_PROVIDER_ADAPTER", "GENERATION_LIMIT_ENABLED", "LIVE_POI_ENABLED", mode="before",
    )
    @classmethod
    def parse_boolish(cls, v):
        """Accept common deployment strings such as DEBUG=release without crashing startup."""
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on", "debug", "development"}:
                return True
            if normalized in {"0", "false", "no", "n", "off", "release", "production"}:
                return False
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

