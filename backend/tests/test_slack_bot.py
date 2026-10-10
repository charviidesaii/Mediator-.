"""Tests for Slack Bolt integration, Socket Mode service, and loop prevention."""

import os
import tempfile
from unittest.mock import MagicMock
import pytest

from app.models.schemas import ProjectCreate
from app.services.supabase import StorageService
from app.slack.bot import _is_duplicate_event, create_slack_app
from app.slack.service import SlackIntegrationService
from app.workflows.alignment import AlignmentWorkflow


@pytest.mark.asyncio
async def test_slack_clean_text_and_mentions():
    """Validates Slack message sanitization, mention stripping, and link extraction."""
    service = SlackIntegrationService()

    raw1 = "<@U12345678> The project deadline is Saturday and I believe Taylor owns deployment."
    cleaned1 = service.clean_slack_text(raw1)
    assert cleaned1 == "The project deadline is Saturday and I believe Taylor owns deployment."

    raw2 = "Check out <#C12345|announcements> and <https://example.com|our docs>"
    cleaned2 = service.clean_slack_text(raw2)
    assert "announcements" in cleaned2
    assert "our docs" in cleaned2


@pytest.mark.asyncio
async def test_slack_channel_context_extraction():
    """Validates harvesting user messages and ignoring bot/system events."""
    service = SlackIntegrationService()

    # Mock Slack WebClient
    mock_client = MagicMock()
    mock_client.conversations_history.return_value = {
        "ok": True,
        "messages": [
            {"user": "U_ALEX", "text": "<@U_BOT> The project deadline is Saturday.", "ts": "100.1"},
            {"user": "U_BOT", "bot_id": "B_BOT", "text": "I am a bot reply", "ts": "100.2"},
            {"user": "U_SAM", "text": "The project deadline is Sunday.", "ts": "100.3"},
            {"user": "U_TAYLOR", "subtype": "channel_join", "text": "joined", "ts": "100.4"},
        ],
    }
    mock_client.users_info.side_effect = lambda user: {
        "ok": True,
        "user": {"profile": {"display_name": "Alex" if user == "U_ALEX" else "Sam"}},
    }

    extracted = await service.extract_channel_context(
        client=mock_client,
        channel_id="C_PROJECT_1",
        bot_user_id="U_BOT",
    )

    assert len(extracted) == 2
    assert extracted[0][0] == "Alex"
    assert "Saturday" in extracted[0][1]
    assert extracted[1][0] == "Sam"
    assert "Sunday" in extracted[1][1]


@pytest.mark.asyncio
async def test_slack_channel_project_mapping_persistence():
    """Validates that a Slack channel maps to a persistent project workspace."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = tmp_db.name

    try:
        storage = StorageService(backend="sqlite")
        storage.db_path = db_path
        await storage.initialize()

        # Map channel C_SQUAD to new project
        project = await storage.get_or_create_project_for_channel(
            channel_id="C_SQUAD_ALPHA",
            channel_name="sprint-alpha",
        )
        assert project.id is not None
        assert "sprint-alpha" in project.title

        # Calling again returns the exact same project ID
        project_again = await storage.get_or_create_project_for_channel(
            channel_id="C_SQUAD_ALPHA",
        )
        assert project_again.id == project.id

        # Verify mapping persists in fresh storage instance
        storage_restart = StorageService(backend="sqlite")
        storage_restart.db_path = db_path
        await storage_restart.initialize()

        mapping = await storage_restart.get_channel_mapping("C_SQUAD_ALPHA")
        assert mapping is not None
        assert mapping["project_id"] == project.id

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_slack_formatting_includes_evidence_and_dashboard_link():
    """Validates Slack Block Kit output contains evidence quotes, proposals, and dashboard link."""
    service = SlackIntegrationService()

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = tmp_db.name

    try:
        storage = StorageService(backend="sqlite")
        storage.db_path = db_path
        await storage.initialize()

        project = await storage.create_project(
            ProjectCreate(title="Slack Alignment Test", description="Testing formatting")
        )

        # Ingest 2 conflicting perspectives
        r1 = await storage.add_response(project.id, "Alex", "The deadline is Saturday.", "slack")
        r2 = await storage.add_response(project.id, "Sam", "The deadline is Sunday.", "slack")

        workflow = AlignmentWorkflow()
        result = await workflow.run(project.id, [r1, r2])

        slack_output = service.format_slack_analysis(result, project_id=project.id)

        assert "blocks" in slack_output
        assert "text" in slack_output
        blocks = slack_output["blocks"]

        # Ensure Header exists
        assert any(b.get("type") == "header" for b in blocks)

        # Ensure Dashboard link and button exist
        has_dashboard_button = any(
            b.get("accessory", {}).get("action_id") == "open_dashboard_button"
            for b in blocks
        )
        assert has_dashboard_button, "Slack report must include an Open Dashboard button"

        # Ensure Governance Guardrail text exists
        has_governance = any(
            "Governance Guardrail" in str(b) for b in blocks
        )
        assert has_governance, "Slack report must emphasize human approval is strictly required"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_slack_event_deduplication():
    """Validates that identical event IDs are deduplicated within the TTL window."""
    evt_id = "test_event_998877"
    assert not _is_duplicate_event(evt_id), "First encounter should not be a duplicate"
    assert _is_duplicate_event(evt_id), "Second encounter must be flagged as duplicate"
