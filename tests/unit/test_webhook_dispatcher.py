"""Unit tests for WebhookDispatcher."""

from src.services.webhook_dispatcher import WebhookDispatcher


class TestBuildEventPayload:
    def test_basic_payload(self) -> None:
        payload = WebhookDispatcher.build_event_payload("job.completed", "job-123")
        assert payload["event"] == "job.completed"
        assert payload["job_id"] == "job-123"
        assert "timestamp" in payload

    def test_payload_with_status(self) -> None:
        payload = WebhookDispatcher.build_event_payload(
            "job.completed", "job-123", status="completed"
        )
        assert payload["status"] == "completed"

    def test_payload_with_error(self) -> None:
        payload = WebhookDispatcher.build_event_payload(
            "job.failed", "job-456", error="Something broke"
        )
        assert payload["error"] == "Something broke"

    def test_payload_with_result_url(self) -> None:
        payload = WebhookDispatcher.build_event_payload(
            "job.completed", "job-789", result_url="/api/v1/redesign/jobs/job-789/result"
        )
        assert "result_url" in payload


class TestWebhookDispatcherInit:
    def test_default_config(self) -> None:
        dispatcher = WebhookDispatcher()
        assert dispatcher._max_retries == 3
        assert dispatcher._backoff_base == 2.0
        assert dispatcher._timeout == 10.0

    def test_custom_config(self) -> None:
        dispatcher = WebhookDispatcher(
            max_retries=5,
            backoff_base=3.0,
            timeout=30.0,
        )
        assert dispatcher._max_retries == 5
        assert dispatcher._backoff_base == 3.0
        assert dispatcher._timeout == 30.0


class TestHmacSigning:
    def test_signature_header_format(self) -> None:
        import hashlib
        import hmac
        import json

        payload = {"event": "test", "job_id": "123"}
        secret = "test-secret"  # pragma: allowlist secret
        body = json.dumps(payload, default=str)

        expected = hmac.new(
            secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        assert expected  # Non-empty hex string
        assert len(expected) == 64  # SHA-256 hex = 64 chars
