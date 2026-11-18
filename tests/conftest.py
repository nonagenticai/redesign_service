"""Shared test fixtures for redesign_service tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import clear_settings_cache


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch):
    """Ensure settings cache is cleared before and after each test."""
    monkeypatch.setenv("API_PORT", "6306")
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture()
def mock_db():
    """Create a mock AsyncSession for database operations."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture()
def mock_redis_client():
    """Create a mock RedisClient."""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=True)
    client.exists = AsyncMock(return_value=False)
    client.ping = AsyncMock(return_value=True)
    return client


@pytest.fixture()
def sample_redesign_job():
    """Create a sample RedesignJob-like object for testing."""

    def _make_job(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "job_id": "test-job-123",
            "tenant_id": "tenant-1",
            "status": "completed",
            "url": "https://example.com",
            "html_content": None,
            "scope": "full_page",
            "style": "modern",
            "page_type": "homepage",
            "critique_findings": None,
            "brand_info": None,
            "site_analysis": None,
            "user_context": None,
            "template_version": "v1",
            "styles": None,
            "variant_count": None,
            "parent_job_id": None,
            "root_job_id": None,
            "iteration_number": 0,
            "feedback_text": None,
            "component_target": None,
            "component_html_path": None,
            "accessibility_score": None,
            "accessibility_report": None,
            "original_screenshot_paths": None,
            "comparison_paths": None,
            "diff_paths": None,
            "webhook_url": None,
            "webhook_secret": None,
            "batch_id": None,
            "priority_score": None,
            "redesigned_html_path": "/path/to/redesign.html",
            "section_html_paths": None,
            "screenshot_paths": None,
            "concept_image_paths": None,
            "html_validation_report": None,
            "input_tokens": None,
            "output_tokens": None,
            "estimated_cost": None,
            "error_message": None,
            "pages_count": 1,
            "created_at": datetime(2024, 1, 1, tzinfo=UTC),
            "started_at": None,
            "completed_at": datetime(2024, 1, 1, 0, 5, tzinfo=UTC),
            "cancelled_at": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    return _make_job


@pytest.fixture()
def sample_variant():
    """Create a sample RedesignVariant-like object."""

    def _make_variant(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "variant_id": "var-123",
            "job_id": "test-job-123",
            "style": "modern",
            "status": "completed",
            "redesigned_html_path": "/path/to/variant.html",
            "screenshot_paths": {"desktop": "/path/to/desktop.png"},
            "error_message": None,
            "created_at": datetime(2024, 1, 1, tzinfo=UTC),
            "completed_at": datetime(2024, 1, 1, 0, 5, tzinfo=UTC),
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    return _make_variant


@pytest.fixture()
def sample_batch():
    """Create a sample BatchJob-like object."""

    def _make_batch(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "batch_id": "batch-123",
            "tenant_id": "tenant-1",
            "status": "completed",
            "total_pages": 3,
            "completed_pages": 2,
            "failed_pages": 1,
            "shared_settings": {"style": "modern", "scope": "full_page"},
            "created_at": datetime(2024, 1, 1, tzinfo=UTC),
            "started_at": None,
            "completed_at": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    return _make_batch
