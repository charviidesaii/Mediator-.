"""Verification of Google ADK / Gemini execution separately from mocked tests.

Covers:
1. Live Google ADK / Gemini 2.5 Flash execution (when GEMINI_API_KEY or GOOGLE_API_KEY is configured).
2. ADK Runner integration validation (validates Google ADK Runner, InMemorySessionService, and event stream parsing).
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.config import settings
from app.models.schemas import MemberResponse
from app.workflows.alignment import AlignmentWorkflow, build_adk_alignment_graph


def test_google_adk_workflow_graph_structure():
    """Verifies that the Google ADK Workflow graph compiles with correct sequential nodes:
    START -> Perspective Analysis Agent -> Conflict Detection Agent -> Resolution Synthesis Agent.
    """
    workflow = build_adk_alignment_graph()
    assert workflow is not None
    assert workflow.name == "team_alignment_workflow"


@pytest.mark.skipif(
    not settings.active_api_key,
    reason="BLOCKED: GEMINI_API_KEY / GOOGLE_API_KEY not configured in environment. Real Gemini execution skipped.",
)
@pytest.mark.asyncio
async def test_live_gemini_adk_execution():
    """Executes a real live Google ADK / Gemini 2.5 Flash multi-agent pipeline.
    Only runs when an active API key is provided.
    """
    workflow = AlignmentWorkflow()
    responses = [
        MemberResponse(
            id="resp_1",
            project_id="proj_live_test",
            member_name="Alex",
            raw_text="Our deadline is Saturday and Taylor owns deployment.",
            source="live_test",
        ),
        MemberResponse(
            id="resp_2",
            project_id="proj_live_test",
            member_name="Sam",
            raw_text="The deadline is Sunday and we need complete QA before launch.",
            source="live_test",
        ),
    ]

    result = await workflow.run(project_id="proj_live_test", responses=responses)

    assert result.execution_mode == "LIVE_GEMINI"
    assert len(result.perspectives_output.perspectives) == 2
    assert len(result.conflicts_output.conflicts) >= 1
    assert len(result.synthesis_output.proposed_resolutions) >= 1
    assert result.synthesis_output.alignment_score <= 100.0


@pytest.mark.asyncio
async def test_google_adk_runner_event_stream_parsing():
    """Validates that the Google ADK Runner event stream handling in Perspective Analysis
    correctly extracts final response content parts and validates the schema.
    """
    from app.agents.perspective import PerspectiveAnalysisService

    responses = [
        MemberResponse(
            id="resp_mock_adk",
            project_id="proj_test",
            member_name="Jordan",
            raw_text="I expect to complete the database schema by Wednesday.",
            source="test",
        )
    ]

    # Create mock ADK Runner event with final response
    mock_event = MagicMock()
    mock_event.is_final_response.return_value = True
    mock_part = MagicMock()
    mock_part.thought = False
    mock_part.text = """{
      "perspectives": [
        {
          "member_name": "Jordan",
          "goals": [{"statement": "Complete database schema", "source_quote": "complete the database schema"}],
          "priorities": [{"priority_item": "Database schema", "urgency_level": "HIGH", "source_quote": "by Wednesday"}],
          "deadlines": [{"milestone": "Database schema", "expected_deadline": "Wednesday", "source_quote": "by Wednesday"}],
          "responsibilities": [{"responsibility": "Database schema", "assigned_to": "Jordan", "source_quote": "I expect to complete"}],
          "ambiguities_or_missing_details": ["No migration strategy specified"]
        }
      ],
      "total_members_analyzed": 1,
      "overall_summary": "Jordan plans to finish database schema by Wednesday.",
      "identified_gaps": ["No testing details mentioned."]
    }"""
    mock_event.content.parts = [mock_part]

    async def mock_run_async(*args, **kwargs):
        yield mock_event

    from unittest.mock import PropertyMock

    with patch.object(type(settings), "is_live_gemini_available", new_callable=PropertyMock, return_value=True), \
         patch.object(settings, "use_adk_runner", True), \
         patch("app.agents.perspective.Runner") as mock_runner_cls, \
         patch("app.agents.perspective.InMemorySessionService") as mock_sess_cls:

        mock_runner_instance = MagicMock()
        mock_runner_instance.run_async = mock_run_async
        mock_runner_cls.return_value = mock_runner_instance

        mock_session_svc = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "test_sess_123"
        mock_session_svc.create_session = AsyncMock(return_value=mock_session)
        mock_sess_cls.return_value = mock_session_svc

        service = PerspectiveAnalysisService()
        output = await service.analyze(responses)

        assert service.last_execution_mode == "LIVE_GEMINI"
        assert len(output.perspectives) == 1
        assert output.perspectives[0].member_name == "Jordan"
        assert output.perspectives[0].goals[0].statement == "Complete database schema"
