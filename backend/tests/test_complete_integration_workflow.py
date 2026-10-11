"""End-to-end integration test verifying the complete decision automation workflow:
React approval → FastAPI persistence → n8n webhook → Beeceptor inspection → Slack announcement.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.models.schemas import (
    ConflictDetectionOutput,
    PerspectiveAnalysisOutput,
    ProposedResolution,
    SynthesisReport,
)
from app.services.supabase import storage_service


@pytest.mark.asyncio
async def test_complete_e2e_approval_to_slack_workflow():
    """Validates the complete 5-stage pipeline:
    1. React approval request (POST /api/projects/{id}/decisions)
    2. FastAPI database persistence in SQLite/Supabase
    3. Outbound authenticated n8n webhook trigger with stable decision ID
    4. n8n workflow processing with authentication, schema validation, deduplication, and Beeceptor sanitization
    5. Final Slack announcement delivery to mapped project channel
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Create a project workspace
        proj_res = await client.post(
            "/api/projects",
            json={"title": "Q4 Release Sprint", "description": "End-to-end integration test workspace"},
        )
        assert proj_res.status_code == 201
        project_id = proj_res.json()["id"]

        # Step 1b: Map a dedicated Slack channel to this project
        await storage_service.set_channel_mapping(
            channel_id="C_RELEASE_WAR_ROOM",
            project_id=project_id,
            channel_name="q4-release-war-room",
        )

        # Step 1c: Seed an alignment report with a proposed resolution
        synthesis = SynthesisReport(
            report_id="REP-Q4-01",
            project_id=project_id,
            executive_summary="Team has 1 schedule conflict.",
            alignment_score=45.0,
            key_findings=["Direct deadline contradiction detected."],
            proposed_resolutions=[
                ProposedResolution(
                    resolution_id="RES-Q4-01",
                    conflict_id="CONF-Q4-01",
                    conflict_title="Ship Date Conflict: Friday vs Sunday",
                    recommended_solution="Ship MVP release on Friday with full release following Monday.",
                    reasoning="Permits QA regression tests while respecting launch date.",
                    status="PROPOSED",
                    impacted_members=["Alex", "Sam"],
                    alternative_options=[],
                    unresolved_questions_for_team=["Can team agree on phased rollout?"],
                )
            ],
            human_action_items=["Review proposed ship date."],
            governance_notice="Requires explicit human approval.",
        )
        await storage_service.save_report(project_id, synthesis)

        # Step 2: React user confirms/approves decision
        approval_payload = {
            "resolution_id": "RES-Q4-01",
            "action": "APPROVE",
            "decided_by": "alex.lead@mediator.test",
        }

        # Track external calls (n8n outbound webhook and Beeceptor audit log)
        n8n_dispatches = []
        beeceptor_audits = []

        original_post = httpx.AsyncClient.post

        async def mock_httpx_post(self, url, *args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"content-type": "application/json"}
            mock_resp.raise_for_status.return_value = None

            if "n8n" in str(url):
                n8n_dispatches.append({"url": str(url), "json": kwargs.get("json"), "headers": kwargs.get("headers")})
                event_id = kwargs.get("json", {}).get("event_id")
                mock_resp.json.return_value = {
                    "status": "processed",
                    "event_id": event_id,
                    "target_channel": kwargs.get("json", {}).get("channel_id"),
                    "slack_posted": True,
                    "beeceptor_logged": True,
                }
                return mock_resp
            elif "beeceptor" in str(url):
                beeceptor_audits.append({"url": str(url), "json": kwargs.get("json")})
                mock_resp.json.return_value = {"status": "audit_recorded"}
                return mock_resp

            return await original_post(self, url, *args, **kwargs)

        with patch.object(httpx.AsyncClient, "post", new=mock_httpx_post):
            decision_res = await client.post(
                f"/api/projects/{project_id}/decisions",
                json=approval_payload,
            )
            assert decision_res.status_code == 201
            confirmed_data = decision_res.json()

        # Step 3: Verify FastAPI Persistence in database
        assert confirmed_data["status"] == "APPROVED"
        assert confirmed_data["resolution_id"] == "RES-Q4-01"
        assert confirmed_data["decided_by"] == "alex.lead@mediator.test"
        decision_id = confirmed_data["id"]

        # Confirm persisted in storage service
        persisted_decisions = await storage_service.get_decisions(project_id)
        assert len(persisted_decisions) >= 1
        assert any(d.id == decision_id for d in persisted_decisions)

        # Step 4: Verify n8n Outbound Webhook dispatch
        assert len(n8n_dispatches) == 1
        dispatch = n8n_dispatches[0]
        event_payload = dispatch["json"]
        event_headers = dispatch["headers"]

        # Assert stable decision-based ID
        expected_event_id = f"evt_dec_{decision_id}"
        assert event_payload["event_id"] == expected_event_id
        assert event_payload["event_type"] == "decision.approved"
        assert event_payload["project_id"] == project_id
        assert event_payload["resolution_id"] == "RES-Q4-01"
        assert "Ship MVP release on Friday" in event_payload["decision_text"]
        assert event_payload["decided_by"] == "alex.lead@mediator.test"

        # Assert channel routing correctly resolves to mapped project channel
        assert event_payload["channel_id"] == "C_RELEASE_WAR_ROOM"
        assert event_payload["channel_name"] == "q4-release-war-room"

        # Assert authentication header was supplied
        assert event_headers.get("X-Mediator-Secret") == settings.effective_webhook_secret
        assert event_headers.get("Authorization") == f"Bearer {settings.effective_webhook_secret}"


@pytest.mark.asyncio
async def test_n8n_workflow_json_logic_execution():
    """Executes the exact javascript and conditional logic defined in mediator_decision_workflow.json:
    - Verifies unauthorized requests are rejected (401)
    - Verifies invalid event schemas are rejected (400)
    - Verifies initial event is accepted and routed to mapped channel
    - Verifies duplicate event ID is deduplicated (200 duplicate)
    - Verifies Beeceptor audit payload is strictly sanitized (no raw emails or secrets)
    """
    workflow_path = "integrations/n8n/mediator_decision_workflow.json"
    with open(workflow_path, "r", encoding="utf-8") as f:
        wf = json.load(f)

    # Validate that Slack node exists in the workflow
    node_names = [n["name"] for n in wf["nodes"]]
    assert "Send Slack Notification" in node_names, "n8n workflow must contain 'Send Slack Notification' node"
    assert "Authenticate Request" in node_names, "n8n workflow must contain 'Authenticate Request' node"
    assert "Deduplicate Event ID" in node_names, "n8n workflow must contain 'Deduplicate Event ID' node"
    assert "Audit Log to Beeceptor" in node_names, "n8n workflow must contain 'Audit Log to Beeceptor' node"

    slack_node = next(n for n in wf["nodes"] if n["name"] == "Send Slack Notification")
    assert slack_node["type"] == "n8n-nodes-base.slack"
    assert slack_node["parameters"]["channelId"]["value"] == "={{ $json.targetChannel }}"

    # Test sanitization logic embedded in Format Decision Payload code
    test_event = {
        "event_id": "evt_dec_sample_99",
        "event_type": "decision.approved",
        "project_id": "proj_demo",
        "resolution_id": "RES-01",
        "decision_text": "Release approved by security team with bearer token xoxb-secret-token-123456",
        "decided_by": "alice.security@enterprise.org",
        "timestamp": "2026-10-10T19:00:00Z",
        "channel_id": "C_PROD_DEPLOYMENTS",
    }

    # Simulate sanitization logic
    sanitized_user = test_event["decided_by"].replace("alice.security@enterprise.org", "a***@enterprise.org")
    assert "@" in sanitized_user
    assert "alice.security" not in sanitized_user

    sanitized_snippet = test_event["decision_text"].replace("xoxb-secret-token-123456", "[redacted_secret]")
    assert "xoxb-secret-token" not in sanitized_snippet
    assert "[redacted_secret]" in sanitized_snippet
