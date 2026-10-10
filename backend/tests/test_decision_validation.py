"""Tests for human decision validation and governance enforcement."""

import pytest
from app.models.schemas import DecisionActionRequest, ProjectCreate
from app.services.supabase import storage_service
from app.workflows.alignment import AlignmentWorkflow


@pytest.mark.asyncio
async def test_decision_validation_rejects_fake_resolution(sample_responses):
    """Verify that attempting to approve/modify a nonexistent resolution ID is strictly rejected."""
    # 1. Create project
    proj = await storage_service.create_project(ProjectCreate(title="Decision Test Project"))

    # 2. Add responses and run analysis
    for r in sample_responses:
        await storage_service.add_response(proj.id, r.member_name, r.raw_text)

    workflow = AlignmentWorkflow()
    result = await workflow.run(proj.id, sample_responses)
    await storage_service.save_report(proj.id, result.synthesis_output)

    # 3. Attempt to record decision with a bogus resolution ID
    fake_action = DecisionActionRequest(
        resolution_id="RES-BOGUS-999",
        action="APPROVE",
        decided_by="Lead PM",
    )
    with pytest.raises(ValueError, match="not found in the project's proposals"):
        await storage_service.record_decision(proj.id, fake_action)


@pytest.mark.asyncio
async def test_decision_modify_requires_custom_text(sample_responses):
    """Verify that action MODIFY requires explicit decision_text."""
    proj = await storage_service.create_project(ProjectCreate(title="Modify Action Project"))
    for r in sample_responses:
        await storage_service.add_response(proj.id, r.member_name, r.raw_text)

    workflow = AlignmentWorkflow()
    result = await workflow.run(proj.id, sample_responses)
    await storage_service.save_report(proj.id, result.synthesis_output)

    valid_res_id = result.synthesis_output.proposed_resolutions[0].resolution_id

    # MODIFY without decision_text should fail
    modify_action_empty = DecisionActionRequest(
        resolution_id=valid_res_id,
        action="MODIFY",
        decision_text=None,
        decided_by="Lead PM",
    )
    with pytest.raises(ValueError, match="requires providing explicit 'decision_text'"):
        await storage_service.record_decision(proj.id, modify_action_empty)

    # MODIFY with decision_text should succeed
    modify_action_valid = DecisionActionRequest(
        resolution_id=valid_res_id,
        action="MODIFY",
        decision_text="Custom agreed compromise: launch Friday 4pm after Taylor approves smoke tests.",
        decided_by="Lead PM",
    )
    decision = await storage_service.record_decision(proj.id, modify_action_valid)
    assert decision.status.value == "MODIFIED"
    assert "Friday 4pm" in decision.decision_text
