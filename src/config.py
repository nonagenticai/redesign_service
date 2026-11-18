"""
Configuration management for redesign_service using Pydantic Settings.

Hierarchical settings with sub-configs.
Follows skill_builder/tts_service config pattern.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""

    url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5456/redesign_service",  # pragma: allowlist secret
        description="PostgreSQL database connection URL",
    )
    pool_size: int = Field(default=10, description="Database connection pool size")
    max_overflow: int = Field(default=20, description="Maximum connections beyond pool_size")
    pool_timeout: int = Field(
        default=30, description="Timeout in seconds for getting a connection from the pool"
    )
    pool_recycle: int = Field(
        default=3600, description="Time in seconds after which connections are recycled"
    )
    echo: bool = Field(default=False, description="Echo SQL statements for debugging")

    model_config = SettingsConfigDict(
        env_prefix="DATABASE_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class AuthSettings(BaseSettings):
    """Authentication configuration settings."""

    enabled: bool = Field(default=True, description="Enable authentication middleware")
    ssl_verify: bool = Field(default=True, description="SSL verification for service connections")
    default_tenant_id: str = Field(default="n8n-dev", description="Default tenant ID for fallback")

    model_config = SettingsConfigDict(
        env_prefix="AUTH_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class RedisSettings(BaseSettings):
    """Redis configuration settings."""

    url: str = Field(default="redis://localhost:6396/0", description="Redis connection URL")
    max_connections: int = Field(default=10, description="Maximum Redis connections in pool")
    socket_timeout: int = Field(default=5, description="Socket timeout in seconds")
    socket_connect_timeout: int = Field(default=5, description="Socket connect timeout in seconds")
    decode_responses: bool = Field(
        default=True, description="Decode responses from bytes to strings"
    )

    model_config = SettingsConfigDict(
        env_prefix="REDIS_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class APISettings(BaseSettings):
    """API server configuration settings."""

    host: str = Field(default="0.0.0.0", description="API server host")  # nosec B104
    port: int = Field(default=6306, description="API server port")
    cors_origins: list[str] | str = Field(
        default=[
            "http://localhost:*",
            "http://127.0.0.1:*",
        ],
        description="CORS allowed origins (comma-separated or JSON list)",
    )
    cors_allow_credentials: bool = Field(default=True, description="Allow credentials in CORS")
    cors_allow_methods: list[str] | str = Field(
        default=["*"], description="Allowed HTTP methods for CORS"
    )
    cors_allow_headers: list[str] | str = Field(
        default=["*"], description="Allowed HTTP headers for CORS"
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    reload: bool = Field(default=False, description="Enable auto-reload on code changes")

    @field_validator("cors_origins", "cors_allow_methods", "cors_allow_headers", mode="before")
    @classmethod
    def parse_list_fields(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            if v.strip():
                return [item.strip() for item in v.split(",") if item.strip()]
            return []
        if isinstance(v, list):
            return v
        return [str(v)]

    model_config = SettingsConfigDict(
        env_prefix="API_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class StorageSettings(BaseSettings):
    """File storage configuration."""

    backend: str = Field(default="local", description="Storage backend: local or minio")
    local_path: str = Field(default="/app/data", description="Local storage path")
    minio_endpoint: str = Field(default="localhost:9000", description="MinIO endpoint")
    minio_access_key: str = Field(default="", description="MinIO access key")
    minio_secret_key: str = Field(default="", description="MinIO secret key")
    minio_bucket: str = Field(default="redesign-service", description="MinIO bucket name")
    minio_secure: bool = Field(default=False, description="Use HTTPS for MinIO")

    model_config = SettingsConfigDict(
        env_prefix="STORAGE_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class LLMSettings(BaseSettings):
    """LLM configuration for HTML generation."""

    api_key: str = Field(default="", description="LLM API key")
    base_url: str = Field(
        default="https://api.deepseek.com", description="OpenAI-compatible API base URL"
    )
    model: str = Field(default="deepseek-chat", description="LLM model ID")
    max_tokens: int = Field(default=8192, description="Max tokens for generation")
    timeout: float = Field(default=300.0, description="Request timeout in seconds")

    model_config = SettingsConfigDict(
        env_prefix="LLM_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class ScreenshotSettings(BaseSettings):
    """Screenshot rendering configuration."""

    enabled: bool = Field(default=True, description="Enable screenshot rendering")
    viewports: list[str] = Field(
        default=["desktop", "tablet", "mobile"],
        description="Viewport sizes to render",
    )
    timeout_ms: int = Field(default=30000, description="Page load timeout in milliseconds")

    model_config = SettingsConfigDict(
        env_prefix="SCREENSHOT_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class DalleSettings(BaseSettings):
    """DALL-E concept image generation configuration."""

    enabled: bool = Field(default=False, description="Enable AI concept image generation")
    api_key: str = Field(default="", description="OpenAI API key for DALL-E")
    model: str = Field(default="dall-e-3", description="DALL-E model")
    size: str = Field(default="1792x1024", description="Image size")
    quality: str = Field(default="hd", description="Image quality")
    count: int = Field(default=2, description="Number of concept images to generate")

    model_config = SettingsConfigDict(
        env_prefix="DALLE_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class TemplateSettings(BaseSettings):
    """Prompt template configuration."""

    version: str = Field(default="v1", description="Template version to use")
    directory: str | None = Field(default=None, description="Override template directory path")

    model_config = SettingsConfigDict(
        env_prefix="TEMPLATE_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class WebhookSettings(BaseSettings):
    """Webhook notification configuration."""

    enabled: bool = Field(default=True, description="Enable webhook notifications")
    max_retries: int = Field(default=3, description="Max webhook delivery attempts")
    backoff_base: float = Field(default=2.0, description="Exponential backoff base in seconds")
    timeout: float = Field(default=10.0, description="Webhook request timeout in seconds")

    model_config = SettingsConfigDict(
        env_prefix="WEBHOOK_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class RedesignSettings(BaseSettings):
    """Redesign-specific configuration."""

    scope: str = Field(default="full_page", description="Redesign scope: full_page or sections")
    style: str = Field(
        default="modern", description="Design style: modern, minimalist, bold, elegant"
    )
    max_pages: int = Field(default=5, description="Maximum pages to redesign per request")
    max_html_chars: int = Field(default=15000, description="Max HTML chars to send to LLM")

    # Feature 3: Custom styles
    max_custom_styles_per_tenant: int = Field(
        default=20, description="Max custom styles per tenant"
    )
    preview_max_tokens: int = Field(
        default=4096, description="Max tokens for style preview generation"
    )

    # Feature 4: A/B variants
    max_variants: int = Field(default=4, description="Maximum style variants per job")
    variant_concurrency: int = Field(default=3, description="Max concurrent variant processing")

    # Feature 5: Iteration/refinement
    max_iterations: int = Field(
        default=10, description="Maximum refinement iterations per root job"
    )
    max_feedback_chars: int = Field(default=2000, description="Maximum feedback text length")

    # Feature 10: Batch processing
    batch_max_concurrency: int = Field(default=3, description="Max concurrent pages in a batch")

    model_config = SettingsConfigDict(
        env_prefix="REDESIGN_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class RateLimitSettings(BaseSettings):
    """Rate limiting configuration."""

    enabled: bool = Field(default=False, description="Enable rate limiting")
    default_rpm: int = Field(default=60, description="Default requests per minute")
    redesign_rpm: int = Field(default=10, description="Redesign requests per minute")
    batch_rpm: int = Field(default=5, description="Batch requests per minute")
    burst_multiplier: float = Field(default=1.5, description="Burst multiplier over limit")

    model_config = SettingsConfigDict(
        env_prefix="RATELIMIT_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class RetentionSettings(BaseSettings):
    """Data retention configuration."""

    retention_days: int = Field(default=30, description="Days to retain job data")
    cleanup_enabled: bool = Field(default=False, description="Enable periodic cleanup")

    model_config = SettingsConfigDict(
        env_prefix="RETENTION_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class LoggingSettings(BaseSettings):
    """Logging configuration settings."""

    level: str = Field(default="INFO", description="Logging level")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log message format",
    )
    date_format: str = Field(default="%Y-%m-%d %H:%M:%S", description="Date format for logs")
    json_logs: bool = Field(default=False, description="Output logs in JSON format")

    @field_validator("level", mode="before")
    @classmethod
    def validate_level(cls, v: Any) -> str:
        if isinstance(v, str):
            v = v.upper()
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if v not in valid_levels:
                raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return str(v)

    model_config = SettingsConfigDict(
        env_prefix="LOG_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class Settings(BaseSettings):
    """Main application settings combining all configuration sections."""

    app_name: str = Field(default="Redesign Service", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    environment: str = Field(
        default="development", description="Environment (development, staging, production)"
    )

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    api: APISettings = Field(default_factory=APISettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    screenshot: ScreenshotSettings = Field(default_factory=ScreenshotSettings)
    dalle: DalleSettings = Field(default_factory=DalleSettings)
    redesign: RedesignSettings = Field(default_factory=RedesignSettings)
    templates: TemplateSettings = Field(default_factory=TemplateSettings)
    webhook: WebhookSettings = Field(default_factory=WebhookSettings)
    ratelimit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    retention: RetentionSettings = Field(default_factory=RetentionSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        if self.api.port == 8000:
            raise ValueError(
                "API port is set to 8000, which is not allowed. "
                "Please use a different port (default: 6306)."
            )

    def get_database_url(self) -> str:
        return self.database.url

    def get_redis_url(self) -> str:
        return self.redis.url

    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def is_development(self) -> bool:
        return self.environment.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear the cached settings instance (useful for testing)."""
    get_settings.cache_clear()
