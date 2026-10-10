"""Unit tests for Agent 3 — Resolution & Synthesis Agent."""

import pytest
from app.agents.perspective import PerspectiveAnalysisService
from app.agents.conflict import ConflictDetectionService
from app.agents.resolution import ResolutionSynthesisService


@pytest.mark.asyncio
async def test_resolution_synthesis(sample_responses):
    """Test generating compromise schedule and recommendations."""
    persp_service = PerspectiveAnalysisService()
    perspectives = await persp_service.analyze(sample_responses)

    conflict_service = ConflictDetectionService()
    conflicts = await conflict_service.detect_conflicts(perspectives)

    resolution_service = ResolutionSynthesisService()
    report = await resolution_service.synthesize("test-project", perspectives, conflicts)

    assert report.alignment_score >= 0.0 and report.alignment_score <= 100.0
    assert len(report.proposed_resolutions) >= 1
    assert len(report.human_action_items) > 0


@pytest.mark.asyncio
async def test_resolutions_never_auto_approved(sample_responses):
    """CRITICAL GOVERNANCE RULE: Verify proposed resolutions are NEVER marked as approved."""
    persp_service = PerspectiveAnalysisService()
    perspectives = await persp_service.analyze(sample_responses)

    conflict_service = ConflictDetectionService()
    conflicts = await conflict_service.detect_conflicts(perspectives)

    resolution_service = ResolutionSynthesisService()
    report = await resolution_service.synthesize("test-project", perspectives, conflicts)

    for res in report.proposed_resolutions:
        # Status MUST be PROPOSED
        assert res.status == "PROPOSED"
        assert res.status != "APPROVED"

    assert "require explicit human team approval" in report.disclaimer


@pytest.mark.asyncio
async def test_unresolved_questions_identified(sample_responses):
    """Verify that unresolved questions requiring team input are formulated."""
    persp_service = PerspectiveAnalysisService()
    perspectives = await persp_service.analyze(sample_responses)

    conflict_service = ConflictDetectionService()
    conflicts = await conflict_service.detect_conflicts(perspectives)

    resolution_service = ResolutionSynthesisService()
    report = await resolution_service.synthesize("test-project", perspectives, conflicts)

    for res in report.proposed_resolutions:
        assert len(res.unresolved_questions_for_team) > 0
        assert len(res.alternative_options) > 0
