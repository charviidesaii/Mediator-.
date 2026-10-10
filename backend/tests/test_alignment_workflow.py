"""Unit and integration tests for the sequential Multi-Agent Alignment Workflow."""

import pytest
from app.models.schemas import MemberResponse
from app.workflows.alignment import AlignmentWorkflow, build_adk_alignment_graph


def test_build_adk_alignment_graph():
    """Verify Google ADK workflow graph construction with sequential nodes."""
    adk_wf = build_adk_alignment_graph()
    assert adk_wf.name == "team_alignment_workflow"
    assert adk_wf.graph is not None

    node_names = [n.name for n in adk_wf.graph.nodes]
    assert "__START__" in node_names
    assert "perspective_analysis_agent" in node_names
    assert "conflict_detection_agent" in node_names
    assert "resolution_synthesis_agent" in node_names


@pytest.mark.asyncio
async def test_full_workflow_execution(workflow, sample_responses):
    """Test full sequential execution: Perspective -> Conflict -> Resolution."""
    result = await workflow.run(project_id="proj-456", responses=sample_responses)

    assert result.project_id == "proj-456"
    assert result.workflow_id.startswith("wf-")

    # Verify stage 1
    assert result.perspectives_output.total_members_analyzed == 3
    # Verify stage 2
    assert len(result.conflicts_output.conflicts) >= 1
    # Verify stage 3
    assert len(result.synthesis_output.proposed_resolutions) >= 1

    # Verify intermediate debug results are persisted
    assert "perspectives" in result.intermediate_results
    assert "conflicts" in result.intermediate_results
    assert "synthesis" in result.intermediate_results

    # Verify all proposed resolutions have status == PROPOSED
    for res in result.synthesis_output.proposed_resolutions:
        assert res.status == "PROPOSED"


@pytest.mark.asyncio
async def test_workflow_extension_agent_hook(workflow, sample_responses):
    """Verify that future extension agents (e.g. Commitment Tracker) can be attached."""
    hook_called = False

    async def mock_commitment_tracker(project_id, intermediates):
        nonlocal hook_called
        hook_called = True
        assert "synthesis" in intermediates

    workflow.register_extension_agent(mock_commitment_tracker)
    await workflow.run(project_id="proj-ext", responses=sample_responses)
    assert hook_called is True
