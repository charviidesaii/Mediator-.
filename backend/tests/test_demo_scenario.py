"""End-to-End Demo Scenario Integration Tests.

Validates the full hackathon scenario with 3 fictional teammates:
1. Alex: "The project deadline is Saturday and I believe Taylor owns deployment."
2. Sam: "The project deadline is Sunday and we need full feature completion."
3. Taylor: "I believe Alex owns deployment, and we must complete thorough testing before launching anything."

Asserts:
- All 3 viewpoints are ingested and attributed to authors.
- Conflict Agent identifies:
  * Deadline disagreement (Saturday vs Sunday).
  * Task ownership confusion (Alex assigns deployment to Taylor; Taylor assigns to Alex).
- Evidence quotes are preserved verbatim from raw input.
- Resolutions are proposed with status PROPOSED (never auto-approved).
- Human team can approve or modify proposals into official binding commitments.
- Data persists across server restarts (simulated via new StorageService on SQLite file).
"""

import os
import tempfile
import pytest

from app.models.schemas import (
    ConflictSeverity,
    ConflictType,
    DecisionActionRequest,
    DecisionStatus,
    ProjectCreate,
    TeamMemberCreate,
)
from app.services.supabase import StorageService
from app.workflows.alignment import AlignmentWorkflow


@pytest.mark.asyncio
async def test_hackathon_demo_three_teammate_conflicts():
    """Validates deadline contradiction and deployment ownership confusion detection."""
    # Use isolated SQLite file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = tmp_db.name

    try:
        storage = StorageService(backend="sqlite")
        storage.db_path = db_path
        await storage.initialize()

        # Step 1: Create Project Workspace
        project = await storage.create_project(
            ProjectCreate(
                title="Hackathon Q4 Mobile Alignment",
                description="Synchronizing sprint launch between Alex, Sam, and Taylor",
            )
        )
        assert project.id is not None
        assert project.title == "Hackathon Q4 Mobile Alignment"

        # Step 2: Add Roster Members
        m_alex = await storage.add_team_member(
            project.id, TeamMemberCreate(name="Alex", role="Frontend Lead", email="alex@team.com")
        )
        m_sam = await storage.add_team_member(
            project.id, TeamMemberCreate(name="Sam", role="Product Lead", email="sam@team.com")
        )
        m_taylor = await storage.add_team_member(
            project.id, TeamMemberCreate(name="Taylor", role="QA Engineer", email="taylor@team.com")
        )
        assert len([m_alex, m_sam, m_taylor]) == 3

        # Step 3: Ingest Conflicting Submissions
        statements = [
            ("Alex", "The project deadline is Saturday and I believe Taylor owns deployment."),
            ("Sam", "The project deadline is Sunday and we need full feature completion."),
            ("Taylor", "I believe Alex owns deployment, and we must complete thorough testing before launching anything."),
        ]

        responses = []
        for name, text in statements:
            resp = await storage.add_response(
                project_id=project.id,
                member_name=name,
                raw_text=text,
                source="hackathon_demo",
            )
            responses.append(resp)

        assert len(responses) == 3
        stored_responses = await storage.get_responses(project.id)
        assert len(stored_responses) == 3

        # Step 4: Run Google ADK Multi-Agent Alignment Workflow
        workflow = AlignmentWorkflow()
        result = await workflow.run(project_id=project.id, responses=responses)

        # Save synthesis output to persistent storage
        await storage.save_report(project.id, result.synthesis_output)

        # -------------------------------------------------------------
        # Verify Agent 1 (Perspective Extraction)
        # -------------------------------------------------------------
        p_out = result.perspectives_output
        assert p_out.total_members_analyzed == 3
        names_analyzed = {p.member_name for p in p_out.perspectives}
        assert names_analyzed == {"Alex", "Sam", "Taylor"}

        alex_perspective = next(p for p in p_out.perspectives if p.member_name == "Alex")
        sam_perspective = next(p for p in p_out.perspectives if p.member_name == "Sam")
        taylor_perspective = next(p for p in p_out.perspectives if p.member_name == "Taylor")

        # Verify deadlines extracted
        assert any(d.expected_deadline == "Saturday" for d in alex_perspective.deadlines)
        assert any(d.expected_deadline == "Sunday" for d in sam_perspective.deadlines)

        # Verify deployment ownership assumptions extracted
        assert any(
            r.responsibility.lower() == "deployment" and r.assigned_to.lower() == "taylor"
            for r in alex_perspective.responsibilities
        )
        assert any(
            r.responsibility.lower() == "deployment" and r.assigned_to.lower() == "alex"
            for r in taylor_perspective.responsibilities
        )

        # -------------------------------------------------------------
        # Verify Agent 2 (Conflict Detection)
        # -------------------------------------------------------------
        c_out = result.conflicts_output
        conflicts = c_out.conflicts
        assert len(conflicts) >= 2, "Expected at least deadline and ownership conflicts"

        # Check Conflict A: Deadline Disagreement (Saturday vs Sunday)
        deadline_conflicts = [
            c for c in conflicts if c.conflict_type == ConflictType.DEADLINE_CONTRADICTION
        ]
        assert len(deadline_conflicts) >= 1, "Must detect deadline disagreement"
        deadline_c = deadline_conflicts[0]
        assert "Alex" in deadline_c.parties_involved and "Sam" in deadline_c.parties_involved
        assert deadline_c.severity == ConflictSeverity.HIGH
        # Verify evidence preservation
        assert any("Saturday" in ev.quote for ev in deadline_c.evidence)
        assert any("Sunday" in ev.quote for ev in deadline_c.evidence)

        # Check Conflict B: Ownership Confusion on Deployment
        resp_conflicts = [
            c for c in conflicts if c.conflict_type == ConflictType.RESPONSIBILITY_OVERLAP_OR_GAP
        ]
        assert len(resp_conflicts) >= 1, "Must detect deployment responsibility confusion"
        resp_c = resp_conflicts[0]
        assert "Alex" in resp_c.parties_involved and "Taylor" in resp_c.parties_involved
        assert resp_c.severity == ConflictSeverity.HIGH
        assert any("Taylor owns deployment" in ev.quote for ev in resp_c.evidence)
        assert any("Alex owns deployment" in ev.quote for ev in resp_c.evidence)

        # -------------------------------------------------------------
        # Verify Agent 3 (Resolution Synthesis)
        # -------------------------------------------------------------
        s_out = result.synthesis_output
        assert len(s_out.proposed_resolutions) >= 2
        # Governance invariant: Must strictly be PROPOSED
        for r in s_out.proposed_resolutions:
            assert r.status == "PROPOSED"
            assert len(r.unresolved_questions_for_team) > 0

        # Verify specific resolution for ownership was generated
        ownership_resolution = next(
            (r for r in s_out.proposed_resolutions if "ownership" in r.conflict_title.lower() or "deployment" in r.conflict_title.lower() or "responsibility" in r.recommended_solution.lower()),
            None
        )
        assert ownership_resolution is not None
        assert "Alex" in ownership_resolution.impacted_members or "Taylor" in ownership_resolution.impacted_members

        # -------------------------------------------------------------
        # Verify Human Decision Sign-off
        # -------------------------------------------------------------
        res_to_approve = s_out.proposed_resolutions[0]
        confirmed_approval = await storage.record_decision(
            project.id,
            DecisionActionRequest(
                resolution_id=res_to_approve.resolution_id,
                action="APPROVE",
                decided_by="Sam (Product Lead)",
                notes="Approved unanimously in sprint kickoff",
            ),
        )
        assert confirmed_approval.status == DecisionStatus.APPROVED
        assert confirmed_approval.resolution_id == res_to_approve.resolution_id
        assert confirmed_approval.decision_text == res_to_approve.recommended_solution

        # Verify Modify Action with custom negotiated compromise
        res_to_modify = s_out.proposed_resolutions[1]
        custom_compromise = "Agreed commitment: Alex configures Docker & CI/CD on Friday; Taylor executes Sunday release deployment."
        confirmed_modify = await storage.record_decision(
            project.id,
            DecisionActionRequest(
                resolution_id=res_to_modify.resolution_id,
                action="MODIFY",
                decision_text=custom_compromise,
                decided_by="Taylor (QA Lead)",
                notes="Pair deployment negotiated between Alex and Taylor",
            ),
        )
        assert confirmed_modify.status == DecisionStatus.MODIFIED
        assert confirmed_modify.decision_text == custom_compromise

        # -------------------------------------------------------------
        # Verify Database Persistence Across Server Restart
        # -------------------------------------------------------------
        # Simulate complete process termination by creating brand-new StorageService
        restarted_storage = StorageService(backend="sqlite")
        restarted_storage.db_path = db_path
        await restarted_storage.initialize()

        reloaded_project = await restarted_storage.get_project(project.id)
        assert reloaded_project is not None
        assert reloaded_project.title == project.title
        assert len(reloaded_project.members) == 3

        reloaded_responses = await restarted_storage.get_responses(project.id)
        assert len(reloaded_responses) == 3

        reloaded_report = await restarted_storage.get_latest_report(project.id)
        assert reloaded_report is not None
        assert reloaded_report.alignment_score == s_out.alignment_score

        reloaded_decisions = await restarted_storage.get_decisions(project.id)
        assert len(reloaded_decisions) == 2
        assert reloaded_decisions[0].status == DecisionStatus.APPROVED
        assert reloaded_decisions[1].status == DecisionStatus.MODIFIED
        assert reloaded_decisions[1].decision_text == custom_compromise

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
