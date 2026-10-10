"""Unit tests for Agent 1 — Perspective Analysis Agent."""

import pytest
from app.agents.perspective import PerspectiveAnalysisService
from app.models.schemas import MemberResponse


@pytest.mark.asyncio
async def test_perspective_extraction(sample_responses):
    """Test extracting goals, priorities, responsibilities, and deadlines from sample responses."""
    service = PerspectiveAnalysisService()
    output = await service.analyze(sample_responses)

    assert output.total_members_analyzed == 3
    assert len(output.perspectives) == 3

    # Check Alex's extracted perspective
    alex = next(p for p in output.perspectives if p.member_name == "Alex")
    assert any("Friday" in d.expected_deadline for d in alex.deadlines)
    assert any("frontend" in g.statement.lower() for g in alex.goals)
    assert len(alex.priorities) > 0
    assert alex.key_quotes[0] == "Our priority is completing the frontend by Friday."

    # Check Sam's extracted perspective
    sam = next(p for p in output.perspectives if p.member_name == "Sam")
    assert any("Thursday" in d.expected_deadline for d in sam.deadlines)
    assert any("launch" in g.statement.lower() for g in sam.goals)

    # Check Taylor's extracted perspective
    taylor = next(p for p in output.perspectives if p.member_name == "Taylor")
    assert any("test" in g.statement.lower() for g in taylor.goals)
    # Testing duration is missing/ambiguous
    assert any("testing" in amb.lower() or "duration" in amb.lower() for amb in taylor.ambiguities_or_missing_details)


@pytest.mark.asyncio
async def test_source_evidence_preservation(sample_responses):
    """Verify that original statements are preserved verbatim in evidence fields."""
    service = PerspectiveAnalysisService()
    output = await service.analyze(sample_responses)

    for p in output.perspectives:
        assert len(p.key_quotes) > 0
        for quote in p.key_quotes:
            assert quote in [r.raw_text for r in sample_responses]


@pytest.mark.asyncio
async def test_empty_responses():
    """Verify handling when no responses are provided."""
    service = PerspectiveAnalysisService()
    output = await service.analyze([])

    assert output.total_members_analyzed == 0
    assert len(output.perspectives) == 0
    assert "No responses" in output.overall_summary
