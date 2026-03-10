"""
FORGE Data API — pydantic-settings configuration.
All values are read from environment variables (or .env file).
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://forge:forge@postgres:5432/forge"
    redis_url: str = "redis://redis:6379/0"

    # ── MinIO / Storage ────────────────────────────────────────────────────
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "forge"
    minio_secret_key: str = "forgedata123"
    minio_bucket: str = "forge-data"
    minio_use_ssl: bool = False

    # ── Jupyter ────────────────────────────────────────────────────────────
    jupyter_gateway_url: str = "http://jupyter:8888"
    jupyter_token: str = ""

    # ── MLflow ─────────────────────────────────────────────────────────────
    mlflow_tracking_uri: str = "http://mlflow:5000"

    # ── Auth ───────────────────────────────────────────────────────────────
    jwt_secret: str = "change-me-in-production-use-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # ── BYOK — LLM Providers ───────────────────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_ai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-02-01"

    # ── App ────────────────────────────────────────────────────────────────
    next_public_api_url: str = "http://localhost/api"
    next_public_ws_url: str = "ws://localhost/api/ws"
    node_env: str = "development"
    app_env: str = "development"

    # ── CORS ───────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000,http://localhost"

    # ── Feature flags ──────────────────────────────────────────────────────
    feature_mlflow_enabled: bool = True
    feature_jupyter_enabled: bool = True
    feature_connectors_enabled: bool = True

    # ── Encryption salt ────────────────────────────────────────────────────
    # Used as PBKDF2 salt for Fernet key derivation — change in production
    encryption_salt: str = "forge_data_encryption_salt_v1"

    @field_validator("database_url", mode="before")
    @classmethod
    def ensure_asyncpg(cls, v: str) -> str:
        """Ensure the database URL uses the asyncpg driver."""
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
