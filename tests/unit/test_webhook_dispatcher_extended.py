"""Extended unit tests for WebhookDispatcher dispatch and logging."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.webhook_dispatcher import WebhookDispatcher


class TestWebhookDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_success_on_first_attempt(self, mock_db) -> None:
        dispatcher = WebhookDispatcher(max_retries=3, backoff_base=0.01, timeout=5.0)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_response.is_success = True

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.services.webhook_dispatcher.httpx.AsyncClient", return_value=mock_client):
            result = await dispatcher.dispatch(
                mock_db,
                job_id="job-1",
                webhook_url="https://hooks.example.com/cb",
                webhook_secret=None,
                event_type="job.completed",
                payload={"event": "job.completed", "job_id": "job-1"},
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_dispatch_with_hmac_signing(self, mock_db) -> None:
        dispatcher = WebhookDispatcher(max_retries=1, backoff_base=0.01, timeout=5.0)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_response.is_success = True

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.services.webhook_dispatcher.httpx.AsyncClient", return_value=mock_client):
            result = await dispatcher.dispatch(
                mock_db,
                job_id="job-1",
                webhook_url="https://hooks.example.com/cb",
                webhook_secret="my-secret",  # pragma: allowlist secret
                event_type="job.completed",
                payload={"event": "job.completed", "job_id": "job-1"},
            )
            assert result is True
            # Verify HMAC header was set
            call_args = mock_client.post.call_args
            headers = call_args.kwargs["headers"]
            assert "X-Webhook-Signature" in headers
            assert headers["X-Webhook-Signature"].startswith("sha256=")

    @pytest.mark.asyncio
    async def test_dispatch_fails_all_retries(self, mock_db) -> None:
        dispatcher = WebhookDispatcher(max_retries=2, backoff_base=0.01, timeout=5.0)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.is_success = False

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.services.webhook_dispatcher.httpx.AsyncClient", return_value=mock_client):
            result = await dispatcher.dispatch(
                mock_db,
                job_id="job-1",
                webhook_url="https://hooks.example.com/cb",
                event_type="job.failed",
                payload={"event": "job.failed"},
            )
            assert result is False
            # Should have retried twice
            assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_dispatch_network_error_retries(self, mock_db) -> None:
        dispatcher = WebhookDispatcher(max_retries=2, backoff_base=0.01, timeout=5.0)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

        with patch("src.services.webhook_dispatcher.httpx.AsyncClient", return_value=mock_client):
            result = await dispatcher.dispatch(
                mock_db,
                job_id="job-1",
                webhook_url="https://hooks.example.com/cb",
                event_type="job.started",
                payload={"event": "job.started"},
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_dispatch_success_after_retry(self, mock_db) -> None:
        dispatcher = WebhookDispatcher(max_retries=3, backoff_base=0.01, timeout=5.0)

        fail_response = MagicMock()
        fail_response.status_code = 503
        fail_response.text = "Service Unavailable"
        fail_response.is_success = False

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.text = "OK"
        success_response.is_success = True

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=[fail_response, success_response])

        with patch("src.services.webhook_dispatcher.httpx.AsyncClient", return_value=mock_client):
            result = await dispatcher.dispatch(
                mock_db,
                job_id="job-1",
                webhook_url="https://hooks.example.com/cb",
                event_type="job.completed",
                payload={"event": "job.completed"},
            )
            assert result is True
            assert mock_client.post.call_count == 2


class TestLogDelivery:
    @pytest.mark.asyncio
    async def test_log_delivery_success(self, mock_db) -> None:
        dispatcher = WebhookDispatcher()
        await dispatcher._log_delivery(
            mock_db,
            job_id="job-1",
            attempt=1,
            event_type="job.completed",
            payload={"event": "test"},
            response_status=200,
            response_text="OK",
            status="delivered",
        )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_delivery_db_error_doesnt_raise(self, mock_db) -> None:
        mock_db.flush.side_effect = Exception("DB error")
        dispatcher = WebhookDispatcher()
        # Should not raise
        await dispatcher._log_delivery(
            mock_db,
            job_id="job-1",
            attempt=1,
            event_type="job.completed",
            payload={"event": "test"},
            response_status=200,
            response_text="OK",
            status="delivered",
        )


class TestBuildEventPayloadExtended:
    def test_all_optional_fields(self) -> None:
        payload = WebhookDispatcher.build_event_payload(
            "job.completed",
            "job-123",
            status="completed",
            error=None,
            result_url="/result",
            batch_id="batch-1",
            variant_id="var-1",
            accessibility_score=85.0,
        )
        assert payload["status"] == "completed"
        assert payload["result_url"] == "/result"
        assert payload["batch_id"] == "batch-1"
        assert payload["variant_id"] == "var-1"
        assert payload["accessibility_score"] == 85.0
        assert "error" not in payload

    def test_with_error(self) -> None:
        payload = WebhookDispatcher.build_event_payload(
            "job.failed",
            "job-456",
            error="LLM timeout",
        )
        assert payload["error"] == "LLM timeout"

    def test_accessibility_score_zero(self) -> None:
        payload = WebhookDispatcher.build_event_payload(
            "job.completed",
            "job-789",
            accessibility_score=0.0,
        )
        assert payload["accessibility_score"] == 0.0
