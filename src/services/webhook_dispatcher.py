"""Webhook notification dispatcher with HMAC signing and retry logic."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import WebhookDeliveryLog

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """Dispatch webhook notifications with HMAC-SHA256 signing and retries."""

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        timeout: float = 10.0,
    ) -> None:
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._timeout = timeout

    async def dispatch(
        self,
        db: AsyncSession,
        *,
        job_id: str,
        webhook_url: str,
        webhook_secret: str | None = None,
        event_type: str,
        payload: dict,
    ) -> bool:
        """Dispatch a webhook notification. Returns True on successful delivery."""
        body = json.dumps(payload, default=str)

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event_type,
            "X-Webhook-Delivery": str(uuid.uuid4()),
        }

        if webhook_secret:
            signature = hmac.new(
                webhook_secret.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        for attempt in range(1, self._max_retries + 1):
            status = "pending"
            response_text = None
            response_status = None

            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        webhook_url,
                        content=body,
                        headers=headers,
                    )
                    response_status = response.status_code
                    response_text = response.text[:1000]

                    if response.is_success:
                        status = "delivered"
                        await self._log_delivery(
                            db,
                            job_id=job_id,
                            attempt=attempt,
                            event_type=event_type,
                            payload=payload,
                            response_status=response_status,
                            response_text=response_text,
                            status=status,
                        )
                        return True

                    status = "failed"
                    logger.warning(
                        "Webhook attempt %d/%d failed for job %s: HTTP %d",
                        attempt,
                        self._max_retries,
                        job_id,
                        response_status,
                    )

            except Exception as exc:
                status = "error"
                response_text = str(exc)[:500]
                logger.warning(
                    "Webhook attempt %d/%d error for job %s: %s",
                    attempt,
                    self._max_retries,
                    job_id,
                    exc,
                )

            await self._log_delivery(
                db,
                job_id=job_id,
                attempt=attempt,
                event_type=event_type,
                payload=payload,
                response_status=response_status,
                response_text=response_text,
                status=status,
            )

            if attempt < self._max_retries:
                backoff = self._backoff_base**attempt
                await asyncio.sleep(backoff)

        return False

    async def _log_delivery(
        self,
        db: AsyncSession,
        *,
        job_id: str,
        attempt: int,
        event_type: str,
        payload: dict,
        response_status: int | None,
        response_text: str | None,
        status: str,
    ) -> None:
        """Log a webhook delivery attempt."""
        try:
            log_entry = WebhookDeliveryLog(
                job_id=job_id,
                attempt_number=attempt,
                event_type=event_type,
                request_payload=payload,
                response_status=response_status,
                response_text=response_text,
                status=status,
                created_at=datetime.now(UTC),
            )
            db.add(log_entry)
            await db.flush()
        except Exception as exc:
            logger.warning("Failed to log webhook delivery: %s", exc)

    @staticmethod
    def build_event_payload(
        event_type: str,
        job_id: str,
        *,
        status: str | None = None,
        error: str | None = None,
        result_url: str | None = None,
        batch_id: str | None = None,
        variant_id: str | None = None,
        accessibility_score: float | None = None,
    ) -> dict:
        """Build a standard webhook event payload."""
        payload: dict = {
            "event": event_type,
            "job_id": job_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if status:
            payload["status"] = status
        if error:
            payload["error"] = error
        if result_url:
            payload["result_url"] = result_url
        if batch_id:
            payload["batch_id"] = batch_id
        if variant_id:
            payload["variant_id"] = variant_id
        if accessibility_score is not None:
            payload["accessibility_score"] = accessibility_score
        return payload
