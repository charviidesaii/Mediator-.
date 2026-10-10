"""Tests verifying multi-agent workflow functionality on arbitrary participants."""

from datetime import datetime, timezone
import pytest
from app.models.schemas import ConflictSeverity, ConflictType, MemberResponse
from app.workflows.alignment import AlignmentWorkflow


@pytest.mark.asyncio
async def test_arbitrary_participants_conflict_detection():
    """Verify that Conflict Agent flags deadline contradiction for arbitrary participant names and dates."""
    now = datetime.now(timezone.utc)
    responses = [
        MemberResponse(
            id="r-1",
            project_id="arbitrary-proj",
            member_name="Elena",
            raw_text="I will finish the backend APIs by Wednesday.",
            source="slack",
            submitted_at=now,
        ),
        MemberResponse(
            id="r-2",
            project_id="arbitrary-proj",
            member_name="Marcus",
            raw_text="We need to launch the entire platform on Tuesday morning.",
            source="slack",
            submitted_at=now,
        ),
        MemberResponse(
            id="r-3",
            project_id="arbitrary-proj",
            member_name="Priya",
            raw_text="Testing is critical before any release goes live.",
            source="slack",
            submitted_at=now,
        ),
    ]

    workflow = AlignmentWorkflow()
    result = await workflow.run("arbitrary-proj", responses)

    # 1. Perspective check for arbitrary participants
    assert result.perspectives_output.total_members_analyzed == 3
    names = [p.member_name for p in result.perspectives_output.perspectives]
    assert "Elena" in names
    assert "Marcus" in names
    assert "Priya" in names

    # 2. Conflict check: Tuesday launch vs Wednesday backend finish
    conflicts = result.conflicts_output.conflicts
    assert len(conflicts) >= 1

    deadline_conflict = next(
        (c for c in conflicts if c.conflict_type == ConflictType.DEADLINE_CONTRADICTION),
        None,
    )
    assert deadline_conflict is not None
    assert "Marcus" in deadline_conflict.parties_involved
    assert "Elena" in deadline_conflict.parties_involved
    assert deadline_conflict.severity == ConflictSeverity.HIGH

    # 3. Resolution check: proposals generated for Elena and Marcus
    assert len(result.synthesis_output.proposed_resolutions) >= 1
    for res in result.synthesis_output.proposed_resolutions:
        assert res.status == "PROPOSED"
        assert len(res.alternative_options) > 0
        assert len(res.unresolved_questions_for_team) > 0
