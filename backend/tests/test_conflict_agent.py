"""Unit tests for Agent 2 — Conflict Detection Agent."""

import pytest
from app.agents.perspective import PerspectiveAnalysisService
from app.agents.conflict import ConflictDetectionService
from app.models.schemas import ConflictSeverity, ConflictType


@pytest.mark.asyncio
async def test_conflict_detection_deadline_mismatch(sample_responses):
    """Verify that Conflict Agent flags Thursday vs Friday deadline contradiction."""
    persp_service = PerspectiveAnalysisService()
    perspectives = await persp_service.analyze(sample_responses)

    conflict_service = ConflictDetectionService()
    conflicts_out = await conflict_service.detect_conflicts(perspectives)

    assert len(conflicts_out.conflicts) >= 1

    # Check the deadline contradiction
    deadline_conflict = next(
        (c for c in conflicts_out.conflicts if c.conflict_type == ConflictType.DEADLINE_CONTRADICTION),
        None,
    )
    assert deadline_conflict is not None
    assert "Alex" in deadline_conflict.parties_involved
    assert "Sam" in deadline_conflict.parties_involved
    assert deadline_conflict.severity == ConflictSeverity.HIGH
    assert len(deadline_conflict.evidence) >= 2


@pytest.mark.asyncio
async def test_conflict_detection_testing_gap(sample_responses):
    """Verify that Conflict Agent identifies Taylor's unbudgeted testing requirement."""
    persp_service = PerspectiveAnalysisService()
    perspectives = await persp_service.analyze(sample_responses)

    conflict_service = ConflictDetectionService()
    conflicts_out = await conflict_service.detect_conflicts(perspectives)

    # Check for unbudgeted testing / information gap
    gap_conflict = next(
        (c for c in conflicts_out.conflicts if "Taylor" in c.parties_involved and "Sam" in c.parties_involved),
        None,
    )
    assert gap_conflict is not None
    assert gap_conflict.severity in [ConflictSeverity.MEDIUM, ConflictSeverity.HIGH]


@pytest.mark.asyncio
async def test_compatible_differences_identified(sample_responses):
    """Verify that the agent distinguishes compatible differences from direct disagreements."""
    persp_service = PerspectiveAnalysisService()
    perspectives = await persp_service.analyze(sample_responses)

    conflict_service = ConflictDetectionService()
    conflicts_out = await conflict_service.detect_conflicts(perspectives)

    assert len(conflicts_out.compatible_differences) > 0
    assert any("Alex" in cd and "Taylor" in cd for cd in conflicts_out.compatible_differences)
