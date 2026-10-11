"""Outbound webhook service for n8n automation following human-approved decisions.

Guarantees:
- Dispatches webhook events strictly on human 'APPROVE' or 'MODIFY' actions.
- Never triggers for 'REJECT' or unapproved 'PROPOSED' resolutions.
- Non-blocking & fault-tolerant: Delivery errors do not roll back or compromise confirmed database decisions.
"""

import logging
import uuid
from typing import Any, Dict, Optional
import httpx

from app.config import settings
from app.models.schemas import ConfirmedDecision, DecisionActionRequest

logger = logging.getLogger(__name__)


async def trigger_n8n_decision_webhook(
    project_id: str,
    action: DecisionActionRequest,
    confirmed: ConfirmedDecision,
) -> Optional[Dict[str, Any]]:
    """Dispatches a confirmed decision event to the configured n8n webhook URL.

    Payload format expected by n8n:
    - event_id: str
    - event_type: "decision.approved" | "decision.modified"
    - project_id: str
    - resolution_id: str
    - decision_text: str
    - decided_by: str
    - timestamp: ISO 8601 string
    """
    if action.action not in ["APPROVE", "MODIFY"]:
        logger.info(f"Skipping n8n webhook dispatch for non-approval action: {action.action}")
        return None

    webhook_url = settings.n8n_webhook_url
    if not webhook_url:
        logger.info("N8N_WEBHOOK_URL is not set. Skipping outbound webhook dispatch.")
        return None

    event_type = "decision.approved" if action.action == "APPROVE" else "decision.modified"
    event_id = f"evt_{uuid.uuid4().hex[:12]}"

    payload = {
        "event_id": event_id,
        "event_type": event_type,
        "project_id": project_id,
        "resolution_id": confirmed.resolution_id,
        "decision_text": confirmed.decision_text,
        "decided_by": confirmed.decided_by,
        "timestamp": confirmed.decided_at.isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            data = response.json() if "application/json" in content_type else {"raw": response.text}
            logger.info(f"Successfully posted decision event {event_id} to n8n ({webhook_url}): {data}")
            return data
    except Exception as err:
        # Fault-tolerant: Webhook errors must NEVER undo saved database decisions or raise to client
        logger.error(
            f"Failed to post decision event {event_id} to n8n webhook at {webhook_url}: {err}",
            exc_info=True,
        )
        return None
