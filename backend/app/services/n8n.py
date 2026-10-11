"""Outbound webhook service for n8n automation following human-approved decisions.

Guarantees:
- Dispatches webhook events strictly on human 'APPROVE' or 'MODIFY' actions.
- Never triggers for 'REJECT' or unapproved 'PROPOSED' resolutions.
- Non-blocking & fault-tolerant: Delivery errors do not roll back or compromise confirmed database decisions.
"""

import asyncio
import logging
from typing import Any, Dict, Optional
import httpx

from app.config import settings
from app.models.schemas import ConfirmedDecision, DecisionActionRequest
from app.services.supabase import storage_service

logger = logging.getLogger(__name__)


async def trigger_n8n_decision_webhook(
    project_id: str,
    action: DecisionActionRequest,
    confirmed: ConfirmedDecision,
) -> Optional[Dict[str, Any]]:
    """Dispatches a confirmed decision event to the configured n8n webhook URL.

    Guarantees:
    - Stable decision-based event ID (evt_dec_<confirmed_id>) for exact deduplication across retries.
    - Authenticated transmission using X-Mediator-Secret and Authorization headers.
    - Retry-safe delivery with exponential backoff on transient errors.
    - Ingestion of mapped project Slack channel destination.
    - Non-blocking & fault-tolerant: Errors never rollback or compromise saved database decisions.
    """
    if action.action not in ["APPROVE", "MODIFY"]:
        logger.info(f"Skipping n8n webhook dispatch for non-approval action: {action.action}")
        return None

    webhook_url = settings.n8n_webhook_url
    if not webhook_url:
        logger.info("N8N_WEBHOOK_URL is not set. Skipping outbound webhook dispatch.")
        return None

    event_type = "decision.approved" if action.action == "APPROVE" else "decision.modified"
    # Stable decision-based event ID guarantees deduplication on retries
    event_id = f"evt_dec_{confirmed.id}"

    # Determine mapped Slack channel for this project
    try:
        channel_mapping = await storage_service.get_channel_mapping_for_project(project_id)
    except Exception as chan_err:
        logger.warning(f"Failed to lookup channel mapping for project {project_id}: {chan_err}")
        channel_mapping = None

    channel_id = (
        channel_mapping.get("channel_id")
        if channel_mapping
        else getattr(settings, "slack_default_channel", "#general")
    )
    channel_name = (
        channel_mapping.get("channel_name")
        if channel_mapping and channel_mapping.get("channel_name")
        else "general"
    )

    payload = {
        "event_id": event_id,
        "event_type": event_type,
        "project_id": project_id,
        "resolution_id": confirmed.resolution_id,
        "decision_text": confirmed.decision_text,
        "decided_by": confirmed.decided_by,
        "timestamp": confirmed.decided_at.isoformat(),
        "channel_id": channel_id,
        "channel_name": channel_name,
    }

    headers = {
        "Content-Type": "application/json",
        "X-Mediator-Secret": settings.effective_webhook_secret,
        "Authorization": f"Bearer {settings.effective_webhook_secret}",
    }

    max_retries = 3
    backoff = 0.5

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json=payload, headers=headers)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                data = response.json() if "application/json" in content_type else {"raw": response.text}
                logger.info(
                    f"Successfully posted decision event {event_id} to n8n ({webhook_url}) on attempt {attempt}: {data}"
                )
                return data
        except Exception as err:
            logger.warning(
                f"Attempt {attempt}/{max_retries} failed sending event {event_id} to n8n ({webhook_url}): {err}"
            )
            if attempt < max_retries:
                await asyncio.sleep(backoff)
                backoff *= 2
            else:
                # Fault-tolerant: Webhook errors must NEVER undo saved database decisions or raise to client
                logger.error(
                    f"Exhausted retries for decision event {event_id} to n8n webhook at {webhook_url}: {err}",
                    exc_info=True,
                )
                return None

