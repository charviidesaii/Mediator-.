"""Tests for n8n outbound webhook automation and fault tolerance."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from app.models.schemas import ConfirmedDecision, DecisionActionRequest, DecisionStatus
from app.services.n8n import trigger_n8n_decision_webhook


@pytest.mark.asyncio
async def test_n8n_webhook_dispatches_on_approve():
    """Validates that APPROVE action dispatches the standardized payload to n8n."""
    action = DecisionActionRequest(
        resolution_id="res_7",
        action="APPROVE",
        decided_by="david@mediator.app",
    )
    confirmed = ConfirmedDecision(
        id="dec_1",
        project_id="proj_42",
        resolution_id="res_7",
        action="APPROVE",
        status=DecisionStatus.APPROVED,
        decision_text="Ship v2 API on Friday",
        decided_by="david@mediator.app",
        decided_at=datetime.now(timezone.utc),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"status": "processed", "event_id": "evt_test"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        res = await trigger_n8n_decision_webhook("proj_42", action, confirmed)

        assert res is not None
        assert res.get("status") == "processed"
        assert mock_post.called

        called_payload = mock_post.call_args[1]["json"]
        assert called_payload["event_type"] == "decision.approved"
        assert called_payload["project_id"] == "proj_42"
        assert called_payload["resolution_id"] == "res_7"
        assert called_payload["decided_by"] == "david@mediator.app"
        assert called_payload["decision_text"] == "Ship v2 API on Friday"


@pytest.mark.asyncio
async def test_n8n_webhook_dispatches_on_modify():
    """Validates that MODIFY action dispatches event_type 'decision.modified'."""
    action = DecisionActionRequest(
        resolution_id="res_8",
        action="MODIFY",
        decided_by="david@mediator.app",
        custom_decision="Modified ship date to Monday",
    )
    confirmed = ConfirmedDecision(
        id="dec_2",
        project_id="proj_42",
        resolution_id="res_8",
        action="MODIFY",
        status=DecisionStatus.APPROVED,
        decision_text="Modified ship date to Monday",
        decided_by="david@mediator.app",
        decided_at=datetime.now(timezone.utc),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"status": "processed"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        res = await trigger_n8n_decision_webhook("proj_42", action, confirmed)

        assert res is not None
        called_payload = mock_post.call_args[1]["json"]
        assert called_payload["event_type"] == "decision.modified"
        assert called_payload["decision_text"] == "Modified ship date to Monday"


@pytest.mark.asyncio
async def test_n8n_webhook_skips_reject():
    """Validates that REJECT action never sends an outbound webhook."""
    action = DecisionActionRequest(
        resolution_id="res_9",
        action="REJECT",
        decided_by="david@mediator.app",
    )
    confirmed = ConfirmedDecision(
        id="dec_3",
        project_id="proj_42",
        resolution_id="res_9",
        action="REJECT",
        status=DecisionStatus.REJECTED,
        decision_text="Rejected proposal",
        decided_by="david@mediator.app",
        decided_at=datetime.now(timezone.utc),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        res = await trigger_n8n_decision_webhook("proj_42", action, confirmed)
        assert res is None
        assert not mock_post.called


@pytest.mark.asyncio
async def test_n8n_webhook_failure_does_not_raise():
    """Validates that network failure or HTTP 500 from n8n is handled gracefully without raising."""
    action = DecisionActionRequest(
        resolution_id="res_10",
        action="APPROVE",
        decided_by="david@mediator.app",
    )
    confirmed = ConfirmedDecision(
        id="dec_4",
        project_id="proj_42",
        resolution_id="res_10",
        action="APPROVE",
        status=DecisionStatus.APPROVED,
        decision_text="Commitment text",
        decided_by="david@mediator.app",
        decided_at=datetime.now(timezone.utc),
    )

    with patch("httpx.AsyncClient.post", side_effect=Exception("Connection refused")):
        res = await trigger_n8n_decision_webhook("proj_42", action, confirmed)
        # Must return None and not raise an exception
        assert res is None
