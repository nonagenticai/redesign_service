"""Unit tests for configuration module."""

from __future__ import annotations

import pytest

from src.config import (
    APISettings,
    AuthSettings,
    DatabaseSettings,
    LLMSettings,
    LoggingSettings,
    RateLimitSettings,
    RedesignSettings,
    RedisSettings,
    RetentionSettings,
    ScreenshotSettings,
    Settings,
    StorageSettings,
    TemplateSettings,
    WebhookSettings,
    clear_settings_cache,
    get_settings,
)


class TestDatabaseSettings:
    def test_default_url(self) -> None:
        s = DatabaseSettings()
        assert "postgresql" in s.url
        assert s.pool_size == 10
        assert s.max_overflow == 20
        assert s.pool_timeout == 30
        assert s.pool_recycle == 3600
        assert s.echo is False


class TestAuthSettings:
    def test_defaults(self, monkeypatch) -> None:
        monkeypatch.delenv("AUTH_ENABLED", raising=False)
        s = AuthSettings()
        assert s.enabled is True
        assert s.ssl_verify is True
        assert s.default_tenant_id == "n8n-dev"


class TestRedisSettings:
    def test_defaults(self) -> None:
        s = RedisSettings()
        assert "redis://" in s.url
        assert s.max_connections == 10
        assert s.decode_responses is True


class TestAPISettings:
    def test_defaults(self) -> None:
        s = APISettings()
        assert s.port == 6306
        assert s.debug is False
        assert s.reload is False

    def test_parse_list_fields_string(self) -> None:
        result = APISettings.parse_list_fields("http://localhost, http://127.0.0.1")
        assert result == ["http://localhost", "http://127.0.0.1"]

    def test_parse_list_fields_empty_string(self) -> None:
        result = APISettings.parse_list_fields("")
        assert result == []

    def test_parse_list_fields_none(self) -> None:
        result = APISettings.parse_list_fields(None)
        assert result == []

    def test_parse_list_fields_list(self) -> None:
        result = APISettings.parse_list_fields(["a", "b"])
        assert result == ["a", "b"]

    def test_parse_list_fields_other(self) -> None:
        result = APISettings.parse_list_fields(42)
        assert result == ["42"]


class TestStorageSettings:
    def test_defaults(self) -> None:
        s = StorageSettings()
        assert s.backend == "local"


class TestLLMSettings:
    def test_defaults(self) -> None:
        s = LLMSettings()
        assert s.model == "deepseek-chat"
        assert s.base_url == "https://api.deepseek.com"
        assert s.max_tokens == 8192
        assert s.timeout == 300.0


class TestScreenshotSettings:
    def test_defaults(self) -> None:
        s = ScreenshotSettings()
        assert s.enabled is True
        assert "desktop" in s.viewports
        assert "tablet" in s.viewports
        assert "mobile" in s.viewports


class TestRedesignSettings:
    def test_defaults(self) -> None:
        s = RedesignSettings()
        assert s.scope == "full_page"
        assert s.style == "modern"
        assert s.max_pages == 5
        assert s.max_custom_styles_per_tenant == 20
        assert s.max_variants == 4
        assert s.max_iterations == 10
        assert s.batch_max_concurrency == 3


class TestRateLimitSettings:
    def test_defaults(self) -> None:
        s = RateLimitSettings()
        assert s.enabled is False
        assert s.default_rpm == 60


class TestRetentionSettings:
    def test_defaults(self) -> None:
        s = RetentionSettings()
        assert s.retention_days == 30
        assert s.cleanup_enabled is False


class TestWebhookSettings:
    def test_defaults(self) -> None:
        s = WebhookSettings()
        assert s.enabled is True
        assert s.max_retries == 3
        assert s.backoff_base == 2.0


class TestTemplateSettings:
    def test_defaults(self) -> None:
        s = TemplateSettings()
        assert s.version == "v1"
        assert s.directory is None


class TestLoggingSettings:
    def test_defaults(self) -> None:
        s = LoggingSettings()
        assert s.level == "INFO"
        assert s.json_logs is False

    def test_validate_level_uppercase(self) -> None:
        result = LoggingSettings.validate_level("debug")
        assert result == "DEBUG"

    def test_validate_level_invalid(self) -> None:
        with pytest.raises(ValueError, match="Invalid log level"):
            LoggingSettings.validate_level("VERBOSE")


class TestSettings:
    def test_default_settings(self) -> None:
        s = Settings()
        assert s.app_name == "Redesign Service"
        assert s.environment == "development"
        assert isinstance(s.database, DatabaseSettings)
        assert isinstance(s.auth, AuthSettings)
        assert isinstance(s.redis, RedisSettings)

    def test_get_database_url(self) -> None:
        s = Settings()
        assert "postgresql" in s.get_database_url()

    def test_get_redis_url(self) -> None:
        s = Settings()
        assert "redis://" in s.get_redis_url()

    def test_is_production(self) -> None:
        s = Settings()
        assert s.is_production() is False

    def test_is_development(self) -> None:
        s = Settings()
        assert s.is_development() is True

    def test_port_8000_rejected(self, monkeypatch) -> None:
        clear_settings_cache()
        monkeypatch.setenv("API_PORT", "8000")
        clear_settings_cache()
        with pytest.raises(ValueError, match="8000"):
            Settings()

    def test_validate_configuration_ok_port(self) -> None:
        clear_settings_cache()
        s = Settings()
        # Should not raise for the default port 6306
        assert s.api.port != 8000


class TestGetSettings:
    def test_returns_settings_instance(self) -> None:
        clear_settings_cache()
        s = get_settings()
        assert isinstance(s, Settings)

    def test_cached(self) -> None:
        clear_settings_cache()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_clear_cache(self) -> None:
        clear_settings_cache()
        s1 = get_settings()
        clear_settings_cache()
        s2 = get_settings()
        # After clearing cache, a new instance is created
        assert s1 is not s2
