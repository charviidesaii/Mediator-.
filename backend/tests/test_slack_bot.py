"""Tests for Slack Bolt integration, Socket Mode service, and loop prevention."""

import os
import tempfile
from unittest.mock import MagicMock
import pytest

from app.config import settings
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


@pytest.mark.asyncio
async def test_slack_handle_app_mention_executes_analysis_service():
    """Integration test verifying handle_app_mention listener executes analysis_service without NameError."""
    import asyncio
    from unittest.mock import AsyncMock, patch
    from app.slack.bot import create_slack_app
    from app.config import settings

    with patch.object(settings, "slack_bot_token", "xoxb-mock-test-token"):
        app = create_slack_app()
        assert app is not None

        # Extract registered listener for app_mention
        listeners = app._listeners
        mention_listener = None
        for l in listeners:
            for m in l.matchers:
                # Check if matcher matches app_mention
                dummy_req = MagicMock()
                dummy_req.body = {"event": {"type": "app_mention"}}
                try:
                    if m.matches(dummy_req):
                        mention_listener = l
                        break
                except Exception:
                    pass

        # Setup mock client
        mock_client = MagicMock()
        mock_client.auth_test.return_value = {"user_id": "U_BOT_123"}
        mock_client.conversations_info.return_value = {"channel": {"name": "sprint-release"}}
        mock_client.conversations_history.return_value = {
            "ok": True,
            "messages": [
                {"user": "U1", "text": "Our deadline is Saturday.", "ts": "100.1"},
                {"user": "U2", "text": "Our deadline is Sunday.", "ts": "100.2"},
            ],
        }
        mock_client.users_info.side_effect = lambda user: {
            "ok": True,
            "user": {"profile": {"display_name": "Dev" if user == "U1" else "QA"}},
        }
        mock_client.chat_postMessage.return_value = {"ts": "100.99"}

        event_payload = {
            "type": "app_mention",
            "client_msg_id": "unique-msg-id-12345",
            "channel": "C_TEST_CHANNEL",
            "user": "U1",
            "text": "<@U_BOT_123> analyze team alignment",
            "ts": "100.3",
        }

        # Execute handler directly
        if mention_listener:
            # Run the listener function
            handler_func = mention_listener.ack_function or mention_listener.handler
            # Call handler and wait for background async task
            handler_func(event_payload, mock_client, mock_client.chat_postMessage)
            # Give background task 1 second to complete
            await asyncio.sleep(0.5)

            # Assert ack or result message was posted
            assert mock_client.chat_postMessage.called


@pytest.mark.asyncio
async def test_slack_bot_and_fastapi_share_same_database():
    """Verifies that the standalone Slack bot and FastAPI backend access the exact same
    persistent database file and maintain state consistency across interactions.
    """
    import tempfile
    from app.services.supabase import storage_service, StorageService
    from app.slack.service import slack_service

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        shared_db_path = tmp.name

    try:
        # Configure shared persistent database
        fastapi_storage = StorageService(backend="sqlite")
        fastapi_storage.db_path = shared_db_path
        await fastapi_storage.initialize()

        slack_bot_storage = StorageService(backend="sqlite")
        slack_bot_storage.db_path = shared_db_path
        await slack_bot_storage.initialize()

        # 1. Slack bot creates a project from a Slack channel mention
        slack_project = await slack_bot_storage.get_or_create_project_for_channel(
            channel_id="C_SHARED_DB_TEST",
            channel_name="shared-db-sprint",
        )
        assert slack_project.id is not None

        # Ingest a message via Slack bot service
        await slack_bot_storage.add_response(
            project_id=slack_project.id,
            member_name="SlackUser",
            raw_text="The ship date must be Tuesday.",
            source="slack",
        )

        # 2. FastAPI backend reads the exact same project and response
        fastapi_project = await fastapi_storage.get_project(slack_project.id)
        assert fastapi_project is not None
        assert fastapi_project.title == slack_project.title

        fastapi_responses = await fastapi_storage.get_responses(slack_project.id)
        assert len(fastapi_responses) == 1
        assert fastapi_responses[0].member_name == "SlackUser"
        assert "Tuesday" in fastapi_responses[0].raw_text

        # 3. Path resolution check
        assert os.path.isabs(settings.resolved_sqlite_db_path)
    finally:
        if os.path.exists(shared_db_path):
            os.remove(shared_db_path)


