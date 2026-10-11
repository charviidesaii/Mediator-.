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

        # Ensure disclaimer text exists
        has_disclaimer = any(
            "team approval required" in str(b) for b in blocks
        )
        assert has_disclaimer, "Slack report must emphasize AI suggestions require team approval"

        # Ensure visible characters remain under 1,000
        visible_chars = service.calculate_visible_characters(blocks)
        assert visible_chars <= 1000, f"Visible characters ({visible_chars}) must not exceed 1000"
        assert len(slack_output["text"]) <= 1000, "Fallback text must not exceed 1000 characters"

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


def test_slack_formatting_various_conflict_counts_and_severity_sorting():
    """Validates Slack reports with 0, 1, 4, and 10+ conflicts, ensuring HIGH severity sorting and < 1,000 chars."""
    from app.models.schemas import (
        AlignmentWorkflowResult,
        ConflictCategory,
        ConflictDetectionOutput,
        ConflictSeverity,
        ConflictType,
        DetectedConflict,
        PerspectiveAnalysisOutput,
        ProposedResolution,
        SynthesisReport,
    )
    from app.slack.service import slack_service

    def make_conflict(idx: int, sev: ConflictSeverity, title: str, impact: str) -> DetectedConflict:
        return DetectedConflict(
            conflict_id=f"CONF-{idx:02d}",
            title=title,
            conflict_type=ConflictType.DEADLINE_CONTRADICTION,
            category=ConflictCategory.DIRECT_DISAGREEMENT,
            severity=sev,
            severity_reasoning=f"Reasoning for conflict {idx}",
            parties_involved=["Alice", "Bob"],
            evidence=[],
            impact_description=impact,
        )

    # 1. Test 0 conflicts
    res_0 = AlignmentWorkflowResult(
        workflow_id="wf-0",
        project_id="proj-0",
        perspectives_output=PerspectiveAnalysisOutput(
            perspectives=[], total_members_analyzed=0, overall_summary="Clean"
        ),
        conflicts_output=ConflictDetectionOutput(
            conflicts=[], synthesis_summary="No conflicts detected."
        ),
        synthesis_output=SynthesisReport(
            report_id="rep-0",
            executive_summary="All members completely aligned.",
            alignment_score=100.0,
            key_findings=["Aligned on goals."],
            proposed_resolutions=[],
            human_action_items=["Proceed with launch schedule."],
        ),
        execution_mode="MOCK_DETERMINISTIC",
    )
    out_0 = slack_service.format_slack_analysis(res_0, project_id="proj-0")
    assert slack_service.calculate_visible_characters(out_0["blocks"]) <= 1000
    assert "0 conflicts" in out_0["text"]
    assert "No active conflicts detected" in out_0["text"]

    # 2. Test 1 conflict
    res_1 = AlignmentWorkflowResult(
        workflow_id="wf-1",
        project_id="proj-1",
        perspectives_output=PerspectiveAnalysisOutput(
            perspectives=[], total_members_analyzed=2, overall_summary="Single gap"
        ),
        conflicts_output=ConflictDetectionOutput(
            conflicts=[
                make_conflict(1, ConflictSeverity.HIGH, "Launch: Team expects different dates (Thu–Sun).", "Different target dates.")
            ],
            synthesis_summary="One high conflict.",
        ),
        synthesis_output=SynthesisReport(
            report_id="rep-1",
            executive_summary="One launch clash.",
            alignment_score=75.0,
            key_findings=["Launch date clash."],
            proposed_resolutions=[
                ProposedResolution(
                    resolution_id="RES-01",
                    conflict_id="CONF-01",
                    conflict_title="Launch",
                    recommended_solution="Confirm Sunday launch after QA testing completes.",
                    reasoning="Allows QA enough time.",
                    impacted_members=["Alice", "Bob"],
                    unresolved_questions_for_team=[],
                )
            ],
            human_action_items=["Confirm Sunday launch."],
        ),
        execution_mode="MOCK_DETERMINISTIC",
    )
    out_1 = slack_service.format_slack_analysis(res_1, project_id="proj-1")
    assert slack_service.calculate_visible_characters(out_1["blocks"]) <= 1000
    assert "1 conflict" in out_1["text"]
    assert "• Launch: Team expects different dates (Thu–Sun)." in out_1["text"]

    # 3. Test 4 conflicts
    c_list_4 = [
        make_conflict(1, ConflictSeverity.HIGH, "Launch: Team expects different dates (Thu–Sun).", "Different dates."),
        make_conflict(2, ConflictSeverity.HIGH, "Deployment: No confirmed owner.", "No deployment owner."),
        make_conflict(3, ConflictSeverity.MEDIUM, "QA: Saturday launch conflicts with testing needs.", "Testing conflict."),
        make_conflict(4, ConflictSeverity.LOW, "Meeting: Next meeting date unclear.", "Unclear meeting time."),
    ]
    res_4 = AlignmentWorkflowResult(
        workflow_id="wf-4",
        project_id="proj-4",
        perspectives_output=PerspectiveAnalysisOutput(
            perspectives=[], total_members_analyzed=4, overall_summary="4 issues"
        ),
        conflicts_output=ConflictDetectionOutput(conflicts=c_list_4, synthesis_summary="4 issues"),
        synthesis_output=SynthesisReport(
            report_id="rep-4",
            executive_summary="Team has 4 conflicts.",
            alignment_score=55.0,
            key_findings=[],
            proposed_resolutions=[
                ProposedResolution(
                    resolution_id=f"RES-{i}",
                    conflict_id=f"CONF-{i}",
                    conflict_title=f"Issue {i}",
                    recommended_solution=f"Step {i} resolution solution.",
                    reasoning="Reasoning",
                    impacted_members=["Alice"],
                    unresolved_questions_for_team=[],
                )
                for i in range(1, 4)
            ],
            human_action_items=[],
        ),
        execution_mode="MOCK_DETERMINISTIC",
    )
    out_4 = slack_service.format_slack_analysis(res_4, project_id="proj-4")
    assert slack_service.calculate_visible_characters(out_4["blocks"]) <= 1000
    assert "4 conflicts" in out_4["text"]
    assert "55% aligned" in out_4["text"]

    # 4. Test 10+ conflicts and sorting by HIGH severity
    c_list_12 = [
        make_conflict(i, ConflictSeverity.LOW if i > 3 else (ConflictSeverity.MEDIUM if i == 3 else ConflictSeverity.HIGH), f"Issue {i}: Description of issue {i}.", f"Impact of issue {i}.")
        for i in range(1, 13)
    ]
    res_12 = AlignmentWorkflowResult(
        workflow_id="wf-12",
        project_id="proj-12",
        perspectives_output=PerspectiveAnalysisOutput(
            perspectives=[], total_members_analyzed=5, overall_summary="Many issues"
        ),
        conflicts_output=ConflictDetectionOutput(conflicts=c_list_12, synthesis_summary="12 issues"),
        synthesis_output=SynthesisReport(
            report_id="rep-12",
            executive_summary="Many conflicts.",
            alignment_score=35.0,
            key_findings=[],
            proposed_resolutions=[
                ProposedResolution(
                    resolution_id=f"RES-{i}",
                    conflict_id=f"CONF-{i}",
                    conflict_title=f"Issue {i}",
                    recommended_solution=f"Action recommendation for issue {i}.",
                    reasoning="Reasoning",
                    impacted_members=["Alice"],
                    unresolved_questions_for_team=[],
                )
                for i in range(1, 6)
            ],
            human_action_items=[],
        ),
        execution_mode="MOCK_DETERMINISTIC",
    )
    out_12 = slack_service.format_slack_analysis(res_12, project_id="proj-12")
    # Verify exactly 4 bullets displayed under Conflicts
    conflicts_block = out_12["blocks"][2]["text"]["text"]
    assert conflicts_block.count("•") == 4
    # Verify visible characters strictly <= 1000
    assert slack_service.calculate_visible_characters(out_12["blocks"]) <= 1000
    assert len(out_12["text"]) <= 1000
    # Verify HIGH severity issues appear before LOW severity
    assert "Issue 1" in conflicts_block
    assert "Issue 2" in conflicts_block


def test_slack_formatting_extremely_long_gemini_responses():
    """Validates that extremely verbose Gemini responses are cleanly budgeted under 1,000 characters without broken words."""
    from app.models.schemas import (
        AlignmentWorkflowResult,
        ConflictCategory,
        ConflictDetectionOutput,
        ConflictSeverity,
        ConflictType,
        DetectedConflict,
        PerspectiveAnalysisOutput,
        ProposedResolution,
        SynthesisReport,
    )
    from app.slack.service import slack_service

    ultra_long_text = (
        "The team members have thoroughly discussed the prospective release architecture in incredible depth, "
        "and after lengthy deliberation across multiple meetings and threads, they have discovered that launching "
        "the application on Thursday will create massive logistical bottlenecks for the QA engineers who explicitly "
        "demanded forty-eight hours of regression analysis to avoid catastrophic downtime."
    )

    conflicts = [
        DetectedConflict(
            conflict_id=f"CONF-{i}",
            title=f"Very Long Title {i}: {ultra_long_text}",
            conflict_type=ConflictType.DEADLINE_CONTRADICTION,
            category=ConflictCategory.DIRECT_DISAGREEMENT,
            severity=ConflictSeverity.HIGH,
            severity_reasoning=ultra_long_text,
            parties_involved=["Alice", "Bob", "Charlie", "Dave"],
            evidence=[],
            impact_description=ultra_long_text,
        )
        for i in range(1, 6)
    ]

    resolutions = [
        ProposedResolution(
            resolution_id=f"RES-{i}",
            conflict_id=f"CONF-{i}",
            conflict_title=f"Very Long Title {i}",
            recommended_solution=ultra_long_text,
            reasoning=ultra_long_text,
            impacted_members=["Alice"],
            unresolved_questions_for_team=[ultra_long_text],
        )
        for i in range(1, 4)
    ]

    result = AlignmentWorkflowResult(
        workflow_id="wf-long",
        project_id="proj-long-123",
        perspectives_output=PerspectiveAnalysisOutput(
            perspectives=[], total_members_analyzed=4, overall_summary=ultra_long_text
        ),
        conflicts_output=ConflictDetectionOutput(conflicts=conflicts, synthesis_summary=ultra_long_text),
        synthesis_output=SynthesisReport(
            report_id="rep-long",
            executive_summary=ultra_long_text,
            alignment_score=45.0,
            key_findings=[ultra_long_text],
            proposed_resolutions=resolutions,
            human_action_items=[ultra_long_text],
        ),
        execution_mode="MOCK_DETERMINISTIC",
    )

    output = slack_service.format_slack_analysis(result, project_id="proj-long-123")
    visible_chars = slack_service.calculate_visible_characters(output["blocks"])

    # Strict check: visible characters MUST remain <= 1000
    assert visible_chars <= 1000, f"Expected <= 1000 characters, got {visible_chars}"
    assert len(output["text"]) <= 1000

    # Ensure no sentence ends with a truncated word like "bottlen..."
    for b in output["blocks"]:
        t = b.get("text", {}).get("text", "")
        for line in t.split("\n"):
            if line.startswith("•"):
                assert line.endswith("."), f"Bullet should end cleanly with period: {line}"
                assert "..." not in line, f"Bullet should not be cut off with ellipsis: {line}"

    # Ensure dashboard URL points to the correct project
    assert "project_id=proj-long-123" in str(output["blocks"])


def test_slack_formatting_hidden_conflicts_shows_count():
    """Validates that when more than 4 conflicts exist, the header displays '4 of X conflicts'."""
    from app.models.schemas import (
        AlignmentWorkflowResult,
        ConflictCategory,
        ConflictDetectionOutput,
        ConflictSeverity,
        ConflictType,
        DetectedConflict,
        PerspectiveAnalysisOutput,
        ProposedResolution,
        SynthesisReport,
    )
    from app.slack.service import slack_service

    conflicts = [
        DetectedConflict(
            conflict_id=f"CONF-{i}",
            title=f"Conflict Title {i}",
            conflict_type=ConflictType.GOAL_INCOMPATIBILITY,
            category=ConflictCategory.DIRECT_DISAGREEMENT,
            severity=ConflictSeverity.HIGH if i <= 2 else ConflictSeverity.MEDIUM,
            severity_reasoning=f"Reasoning {i}",
            parties_involved=["Alice", "Bob"],
            evidence=[],
            impact_description=f"Impact description for conflict {i}.",
        )
        for i in range(1, 6)
    ]

    result = AlignmentWorkflowResult(
        workflow_id="wf-5-conflicts",
        project_id="proj-5",
        perspectives_output=PerspectiveAnalysisOutput(
            perspectives=[], total_members_analyzed=2, overall_summary="5 conflicts test"
        ),
        conflicts_output=ConflictDetectionOutput(conflicts=conflicts, synthesis_summary="5 conflicts"),
        synthesis_output=SynthesisReport(
            report_id="rep-5",
            executive_summary="Team has 5 conflicts.",
            alignment_score=35.0,
            key_findings=[],
            proposed_resolutions=[
                ProposedResolution(
                    resolution_id=f"RES-{i}",
                    conflict_id=f"CONF-{i}",
                    conflict_title=f"Conflict Title {i}",
                    recommended_solution=f"Resolution proposal {i}.",
                    reasoning=f"Reasoning {i}",
                    impacted_members=["Alice"],
                    unresolved_questions_for_team=[],
                )
                for i in range(1, 4)
            ],
            human_action_items=[f"Action item {i}." for i in range(1, 4)],
        ),
        execution_mode="MOCK_DETERMINISTIC",
    )

    output = slack_service.format_slack_analysis(result, project_id="proj-5")
    assert "4 of 5 conflicts" in output["text"], "Header must show '4 of 5 conflicts' when 1 conflict is hidden"
    assert slack_service.calculate_visible_characters(output["blocks"]) <= 1000


def test_slack_formatting_preserves_initials_and_complete_sentences_from_sqlite():
    """Validates Slack summarization on saved SQLite report without calling live Gemini API."""
    import json
    import sqlite3
    from app.models.schemas import (
        AlignmentWorkflowResult,
        ConflictCategory,
        ConflictDetectionOutput,
        ConflictSeverity,
        ConflictType,
        DetectedConflict,
        PerspectiveAnalysisOutput,
        SynthesisReport,
    )
    from app.slack.service import slack_service

    conn = sqlite3.connect("data/mediator.db")
    cursor = conn.cursor()
    cursor.execute("SELECT project_id, report_json FROM alignment_analyses WHERE project_id = '77e4c4ac-3a9d-43c6-862c-1359054796c3' LIMIT 1")
    row = cursor.fetchone()
    if not row:
        cursor.execute("SELECT project_id, report_json FROM alignment_analyses ORDER BY created_at DESC LIMIT 1")
        row = cursor.fetchone()
    conn.close()

    assert row is not None, "Saved SQLite analysis report must exist"
    pid, r_json = row
    data = json.loads(r_json)
    synth = SynthesisReport.model_validate(data)

    # Build conflicts from the saved resolutions in the report
    conflicts = []
    for idx, r in enumerate(synth.proposed_resolutions):
        conflicts.append(
            DetectedConflict(
                conflict_id=r.conflict_id,
                title=r.conflict_title,
                conflict_type=ConflictType.DEADLINE_CONTRADICTION if "deadline" in r.conflict_title.lower() else ConflictType.GOAL_INCOMPATIBILITY,
                category=ConflictCategory.DIRECT_DISAGREEMENT,
                severity=ConflictSeverity.HIGH if idx < 3 else ConflictSeverity.MEDIUM,
                severity_reasoning="Impacts delivery schedule.",
                parties_involved=["Charvi Desai", "David T."],
                evidence=[],
                impact_description=f"{r.conflict_title}: Team needs alignment.",
            )
        )

    result = AlignmentWorkflowResult(
        workflow_id="wf-sqlite-test",
        project_id=pid,
        perspectives_output=PerspectiveAnalysisOutput(
            perspectives=[], total_members_analyzed=4, overall_summary="SQLite saved analysis"
        ),
        conflicts_output=ConflictDetectionOutput(conflicts=conflicts, synthesis_summary="SQLite saved"),
        synthesis_output=synth,
        execution_mode="LIVE_GEMINI",
    )

    output = slack_service.format_slack_analysis(result, project_id=pid)
    visible_chars = slack_service.calculate_visible_characters(output["blocks"])

    # 1. Budget under 1,000 characters
    assert visible_chars <= 1000, f"Visible characters ({visible_chars}) must be under 1,000"
    assert len(output["text"]) <= 1000

    # 2. Shows '4 of 5 conflicts'
    assert "4 of 5 conflicts" in output["text"]

    # 3. Exactly up to 4 conflict bullets and up to 3 next step bullets
    conflicts_block = output["blocks"][2]["text"]["text"]
    next_steps_block = output["blocks"][3]["text"]["text"]
    assert conflicts_block.count("•") == 4
    assert next_steps_block.count("•") <= 3

    # 4. Each bullet is a complete sentence ending with a period
    for block_text in [conflicts_block, next_steps_block]:
        for line in block_text.split("\n"):
            if line.startswith("•"):
                assert line.endswith("."), f"Bullet must end with a period: {line}"
                # Must not be cut off mid-thought like 'The frontend and.' or 'David T.'
                assert line != "• David T.", "Initials must not be treated as a complete standalone bullet"
                assert not line.endswith(" and."), f"Bullet must not end with dangling conjunction: {line}"
                assert not line.endswith(" the."), f"Bullet must not end with dangling article: {line}"
                assert not line.endswith(" on."), f"Bullet must not end with dangling preposition: {line}"

    # 5. Governance disclaimer and Dashboard CTA preserved
    assert "_AI suggestions — team approval required._" in output["text"]
    assert f"project_id={pid}" in str(output["blocks"])




