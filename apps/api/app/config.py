"""
FORGE Data API — pydantic-settings configuration.
All values are read from environment variables (or .env file).
"""

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRETS = frozenset(
    {
        "change-me-in-production-use-openssl-rand-hex-32",
        "test-secret-do-not-use-in-production-32-chars!!",
        "CHANGE_ME_openssl_rand_hex_32",
        "forge_data_encryption_salt_v1",
        "CHANGE_ME_openssl_rand_hex_16",
    }
)
_INSECURE_PASSWORDS = frozenset({"forge", "forgedata123", "CHANGE_ME_openssl_rand_hex_32"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://forge:forge@postgres:5432/forge"
    redis_url: str = "redis://redis:6379/0"

    # MinIO / Storage
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "forge"
    minio_secret_key: str = "forgedata123"
    minio_bucket: str = "forge-data"
    minio_use_ssl: bool = False

    # Jupyter
    jupyter_gateway_url: str = "http://jupyter:8888"
    jupyter_token: str = ""

    # MLflow
    mlflow_tracking_uri: str = "http://mlflow:5000"

    # Auth
    jwt_secret: str = "change-me-in-production-use-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15  # short-lived; refresh rotates it
    jwt_refresh_token_expire_days: int = 30
    setup_init_token: str = ""

    # Encryption — IMPORTANT: set a unique value per deployment.
    # All deployments sharing the same salt + jwt_secret can decrypt each
    # other's stored API keys. Generate with: openssl rand -hex 16
    encryption_salt: str = "forge_data_encryption_salt_v1"

    # BYOK — LLM Providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_ai_api_key: str = ""
    # Leave empty — set via environment variable or the Settings UI.
    # See .env.example for deployment-specific URL patterns.
    ollama_base_url: str = ""
    llama_cpp_base_url: str = ""
    vllm_base_url: str = ""
    gpt4all_base_url: str = ""
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-02-01"

    # App — public-facing URLs (used by the browser)
    next_public_api_url: str = "http://localhost/api"
    next_public_ws_url: str = "ws://localhost/api/ws"
    node_env: str = "development"
    app_env: str = "development"

    # Internal URL used by Jupyter kernels to call the API over the Docker
    # network. Defaults to the Docker service name — works in any standard
    # docker-compose deployment. Override if your API service has a different
    # name or port.
    internal_api_url: str = "http://api:8000"

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost"

    # Feature flags
    feature_mlflow_enabled: bool = True
    feature_jupyter_enabled: bool = True
    feature_connectors_enabled: bool = True

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        """Refuse to start in production with known-weak secrets."""
        if self.app_env != "production":
            return self
        errors: list[str] = []
        if self.jwt_secret in _INSECURE_SECRETS or len(self.jwt_secret) < 32:
            errors.append("JWT_SECRET is weak or default — run: openssl rand -hex 32")
        if self.encryption_salt in _INSECURE_SECRETS or len(self.encryption_salt) < 16:
            errors.append("ENCRYPTION_SALT is weak or default — run: openssl rand -hex 16")
        if self.minio_secret_key in _INSECURE_PASSWORDS:
            errors.append("MINIO_SECRET_KEY is weak or default — run: openssl rand -hex 32")
        if not self.jupyter_token or self.jupyter_token in _INSECURE_PASSWORDS:
            errors.append("JUPYTER_TOKEN must be set in production — run: openssl rand -hex 32")
        if errors:
            raise ValueError(
                "Production secret validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )
        return self

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
